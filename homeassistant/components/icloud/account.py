"""iCloud account."""
from datetime import timedelta
import logging
import operator
from typing import Dict

from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException, PyiCloudNoDevicesException
from pyicloud.services.findmyiphone import DEVICE_STATUS_PENDING, AppleDevice

from homeassistant.components.zone import async_active_zone
from homeassistant.const import ATTR_ATTRIBUTION, ATTR_LATITUDE, ATTR_LONGITUDE
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.event import track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.util import slugify
from homeassistant.util.async_ import run_callback_threadsafe
from homeassistant.util.dt import utcnow
from homeassistant.util.location import distance

from .const import SERVICE_UPDATE

ATTRIBUTION = "Data provided by Apple iCloud"

# entity attributes
ATTR_ACCOUNT_FETCH_INTERVAL = "account_fetch_interval"
ATTR_BATTERY = "battery"
ATTR_BATTERY_STATUS = "battery_status"
ATTR_DEVICE_NAME = "device_name"
ATTR_DEVICE_STATUS = "device_status"
ATTR_LOW_POWER_MODE = "low_power_mode"
ATTR_OWNER_NAME = "owner_fullname"

# services
SERVICE_ICLOUD_PLAY_SOUND = "play_sound"
SERVICE_ICLOUD_DISPLAY_MESSAGE = "display_message"
SERVICE_ICLOUD_LOST_DEVICE = "lost_device"
SERVICE_ICLOUD_UPDATE = "update"
ATTR_ACCOUNT = "account"
ATTR_LOST_DEVICE_MESSAGE = "message"
ATTR_LOST_DEVICE_NUMBER = "number"
ATTR_LOST_DEVICE_SOUND = "sound"

_LOGGER = logging.getLogger(__name__)


class IcloudAccount:
    """Representation of an iCloud account."""

    def __init__(
        self,
        hass: HomeAssistantType,
        username: str,
        password: str,
        icloud_dir: Store,
        max_interval: int,
        gps_accuracy_threshold: int,
    ):
        """Initialize an iCloud account."""
        self.hass = hass
        self._username = username
        self._password = password
        self._fetch_interval = max_interval
        self._max_interval = max_interval
        self._gps_accuracy_threshold = gps_accuracy_threshold

        self._icloud_dir = icloud_dir

        self.api: PyiCloudService = None
        self._owner_fullname = None
        self._family_members_fullname = {}
        self._devices = {}

        self.unsub_device_tracker = None

    def setup(self) -> None:
        """Set up an iCloud account."""
        try:
            self.api = PyiCloudService(
                self._username, self._password, self._icloud_dir.path
            )
        except PyiCloudFailedLoginException as error:
            self.api = None
            _LOGGER.error("Error logging into iCloud Service: %s", error)
            return

        # user_info = None
        # try:
        #     # Gets device owners infos
        #     user_info = self.api.devices.response["userInfo"]
        # except PyiCloudNoDevicesException:
        #     _LOGGER.error("No iCloud device found")
        #     return

        self._owner_fullname = (
            None  # f"{user_info['firstName']} {user_info['lastName']}"
        )

        self._family_members_fullname = {}
        # if user_info.get("membersInfo") is not None:
        #     for prs_id, member in user_info["membersInfo"].items():
        #         self._family_members_fullname[
        #             prs_id
        #         ] = f"{member['firstName']} {member['lastName']}"

        self._devices = {}
        self.update_devices()

    def update_devices(self) -> None:
        """Update iCloud devices."""
        if self.api is None:
            return
        fmi_service = self.api.find_my_iphone

        api_devices = {}
        try:
            fmi_service.refresh_client()
            api_devices = fmi_service.devices
        except PyiCloudNoDevicesException:
            _LOGGER.error("No iCloud device found")
            return
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Unknown iCloud error: %s", err)
            self._fetch_interval = 5
            dispatcher_send(self.hass, SERVICE_UPDATE)
            track_point_in_utc_time(
                self.hass,
                self.keep_alive,
                utcnow() + timedelta(minutes=self._fetch_interval),
            )
            return

        if (
            fmi_service.device(0) is not None
            and fmi_service.device(0).deviceStatus == DEVICE_STATUS_PENDING
        ):
            _LOGGER.error("Pending devices, fetching again in one minute.")
            self._fetch_interval = 1
            track_point_in_utc_time(
                self.hass,
                self.keep_alive,
                utcnow() + timedelta(minutes=self._fetch_interval),
            )
            return

        # Gets devices infos
        for device in api_devices.values():
            device_id = device.id

            if self._devices.get(device_id, None) is not None:
                # Seen device -> updating
                _LOGGER.debug("Updating iCloud device: %s", device.name)
                self._devices[device_id].update(device)
            else:
                # New device, should be unique
                _LOGGER.debug(
                    "Adding iCloud device: %s [model: %s]",
                    device.name,
                    device.rawDeviceModel,
                )
                self._devices[device_id] = IcloudDevice(self, device)

        self._fetch_interval = self._determine_interval()
        # _LOGGER.error(self._fetch_interval)
        # _LOGGER.error(self._devices)
        dispatcher_send(self.hass, SERVICE_UPDATE)
        track_point_in_utc_time(
            self.hass,
            self.keep_alive,
            utcnow() + timedelta(minutes=self._fetch_interval),
        )

    def _determine_interval(self) -> int:
        """Calculate new interval between two API fetch (in minutes)."""
        intervals = {"default": self._max_interval}
        for device in self._devices.values():
            # Max interval if no location
            if device.latitude is None:
                continue

            current_zone = run_callback_threadsafe(
                self.hass.loop,
                async_active_zone,
                self.hass,
                device.latitude,
                device.longitude,
                device.horizontal_accuracy,
            ).result()

            # Max interval if in zone
            if current_zone is not None:
                continue

            zones = (
                self.hass.states.get(entity_id)
                for entity_id in sorted(self.hass.states.entity_ids("zone"))
            )

            distances = []
            for zone_state in zones:
                zone_state_lat = zone_state.attributes[ATTR_LATITUDE]
                zone_state_long = zone_state.attributes[ATTR_LONGITUDE]
                zone_distance = distance(
                    device.latitude, device.longitude, zone_state_lat, zone_state_long,
                )
                distances.append(round(zone_distance / 1000, 1))

            # Max interval if no zone
            if not distances:
                continue
            mindistance = min(distances)

            # Calculate out how long it would take for the device to drive
            # to the nearest zone at 120 km/h:
            interval = round(mindistance / 2, 0)

            # Never poll more than once per minute
            interval = max(interval, 1)

            if interval > 180:
                # Three hour drive?
                # This is far enough that they might be flying
                interval = self._max_interval

            if (
                device.battery_level is not None
                and device.battery_level <= 33
                and mindistance > 3
            ):
                # Low battery - let's check half as often
                interval = interval * 2

            intervals[device.name] = interval

        return max(
            int(min(intervals.items(), key=operator.itemgetter(1))[1]),
            self._max_interval,
        )

    def keep_alive(self, now=None) -> None:
        """Keep the API alive."""
        if self.api is None:
            self.setup()

        if self.api is None:
            return

        self.api.authenticate()
        self.update_devices()

    def get_devices_with_name(self, name: str) -> [any]:
        """Get devices by name."""
        result = []
        name_slug = slugify(name.replace(" ", "", 99))
        for device in self.devices.values():
            if slugify(device.name.replace(" ", "", 99)) == name_slug:
                result.append(device)
        if not result:
            raise Exception(f"No device with name {name}")
        return result

    @property
    def username(self) -> str:
        """Return the account username."""
        return self._username

    @property
    def owner_fullname(self) -> str:
        """Return the account owner fullname."""
        return self._owner_fullname

    @property
    def family_members_fullname(self) -> Dict[str, str]:
        """Return the account family members fullname."""
        return self._family_members_fullname

    @property
    def fetch_interval(self) -> int:
        """Return the account fetch interval."""
        return self._fetch_interval

    @property
    def devices(self) -> Dict[str, any]:
        """Return the account devices."""
        return self._devices


class IcloudDevice:
    """Representation of a iCloud device."""

    def __init__(self, account: IcloudAccount, device: AppleDevice):
        """Initialize the iCloud device."""
        self._account = account

        self._device = device

        # self._name = device.name
        # self._device_id = device.id
        # self._device_class = device.deviceClass
        # self._device_model = device.deviceDisplayName

        # _LOGGER.error(self._name)
        # _LOGGER.error(self._device_id)
        # _LOGGER.error(self._device_class)
        # _LOGGER.error(self._device_model)

        # if device.prsId:
        #     owner_fullname = account.family_members_fullname[
        #         self._status[DEVICE_PERSON_ID]
        #     ]
        # else:
        #     owner_fullname = account.owner_fullname

        self._attrs = {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            ATTR_ACCOUNT_FETCH_INTERVAL: self._account.fetch_interval,
            ATTR_DEVICE_NAME: self.device_model,
            ATTR_DEVICE_STATUS: self.device_status,
            # ATTR_OWNER_NAME: owner_fullname,
            ATTR_BATTERY_STATUS: self.battery_status,
            ATTR_BATTERY: self.battery_level,
            ATTR_LOW_POWER_MODE: device.lowPowerMode,
        }

    def update(self, device: AppleDevice) -> None:
        """Update the iCloud device."""
        self._device = device

        self._attrs[ATTR_DEVICE_STATUS] = self.device_status
        self._attrs[ATTR_BATTERY_STATUS] = self.battery_status
        self._attrs[ATTR_BATTERY] = self.battery_level
        self._attrs[ATTR_LOW_POWER_MODE] = device.lowPowerMode

    def play_sound(self) -> None:
        """Play sound on the device."""
        self._account.api.authenticate()
        _LOGGER.debug("Playing sound for %s", self.name)
        self.device.play_sound()

    def display_message(self, message: str, sound: bool = False) -> None:
        """Display a message on the device."""
        self._account.api.authenticate()
        _LOGGER.debug("Displaying message for %s", self.name)
        self.device.display_message("Subject not working", message, sound)

    def lost_device(self, number: str, message: str) -> None:
        """Make the device in lost state."""
        self._account.api.authenticate()
        if self._device.lostModeCapable:
            _LOGGER.debug("Make device lost for %s", self.name)
            self.device.lost_device(number, message, None)
        else:
            _LOGGER.error("Cannot make device lost for %s", self.name)

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._device.id

    @property
    def name(self) -> str:
        """Return the Apple device name."""
        return self._device.name

    @property
    def device(self) -> AppleDevice:
        """Return the Apple device."""
        return self._device

    @property
    def device_class(self) -> str:
        """Return the Apple device class."""
        return self._device.deviceClass

    @property
    def device_model(self) -> str:
        """Return the Apple device model."""
        return self._device.deviceDisplayName

    @property
    def device_status(self) -> str:
        """Return the Apple device status."""
        return self._device.deviceStatus

    @property
    def battery_level(self) -> int:
        """Return the Apple device battery level."""
        device_battery_level = self._device.batteryLevel
        if device_battery_level is not None:
            return int(device_battery_level * 100)

    @property
    def battery_status(self) -> str:
        """Return the Apple device battery status."""
        return self._device.batteryStatus

    @property
    def horizontal_accuracy(self):
        """Return the Apple device horizontal accuracy."""
        return self._device.horizontalAccuracy

    @property
    def latitude(self):
        """Return the Apple device latitude."""
        return self._device.latitude

    @property
    def longitude(self):
        """Return the Apple device longitude."""
        return self._device.longitude

    @property
    def state_attributes(self) -> Dict[str, any]:
        """Return the attributes."""
        return self._attrs
