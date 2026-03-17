# Vendored from lc7001 v1.0.5 (https://github.com/rtyle/lc7001)
# Original author: Ross Tyler
# License: MIT (https://github.com/rtyle/lc7001/blob/master/LICENSE)
# Modifications: None (vendored as-is to resolve PyPI install failures)

"""asyncio (aio) Legrand Adorne LC7001 Hub interface.

https://www.legrand.us/wiring-devices/electrical-accessories/miscellaneous/adorne-hub/p/lc7001
https://www.amazon.com/Legrand-Q-LC7001-Lighting-Controller/dp/B06XW1MLVF

https://www.legrand.us/solutions/smart-lighting/radio-frequency-lighting-controls
https://developer.legrand.com/documentation/rflc-api-for-lc7001/
"""

import abc
import asyncio
import collections
import contextlib
import json
import logging
import time
from typing import Any, Final, Mapping, MutableMapping

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_logger: Final = logging.getLogger(__name__)


def hash_password(data: bytes) -> bytes:
    """Return a hash of data for turning a password into a key."""
    digest = hashes.Hash(hashes.MD5())
    digest.update(data)
    return digest.finalize()


class Composer:
    """Composer of messages."""

    # message keys
    APP_CONTEXT_ID: Final = "AppContextId"  # echoed in reply
    _ID: Final = "ID"  # echoed in reply
    PROPERTY_LIST: Final = "PropertyList"
    SCENE_LIST: Final = "SceneList"
    SERVICE: Final = "Service"
    SID: Final = "SID"  # json_integer, 0-99
    ZID: Final = "ZID"  # json_integer, 0-99
    ZONE_LIST: Final = "ZoneList"

    # PROPERTY_LIST keys
    NAME: Final = "Name"  # json_string, 1-20 characters

    # SCENE PROPERTY_LIST keys
    DAY_BITS: Final = "DayBits"  # json_integer, DAY_BITS values
    DELTA: Final = "Delta"  # json_integer, minutes before/after TRIGGER_TIME
    FREQUENCY: Final = "Frequency"  # json_integer, FREQUENCY values
    SKIP: Final = "Skip"  # json_boolean, True to skip next trigger
    TRIGGER_TIME: Final = "TriggerTime"  # json_integer, time_t
    TRIGGER_TYPE: Final = "TriggerType"  # json_integer, TRIGGER_TYPE values

    # SCENE PROPERTY_LIST, DAY_BITS values
    SUNDAY: Final = 0
    MONDAY: Final = 1
    TUESDAY: Final = 2
    WEDNESDAY: Final = 3
    THURSDAY: Final = 4
    FRIDAY: Final = 5
    SATURDAY: Final = 6

    # SCENE PROPERTY_LIST, FREQUENCY values
    NONE: Final = 0
    ONCE: Final = 1
    WEEKLY: Final = 2

    # SCENE PROPERTY_LIST, TRIGGER_TYPE values
    REGULAR_TIME: Final = 0
    SUNRISE: Final = 1
    SUNSET: Final = 2

    # SCENE PROPERTY_LIST, ZONE_LIST array, item keys (always with ZID)
    LEVEL: Final = "Lvl"  # json_integer, 1-100 (POWER_LEVEL)
    RR: Final = "RR"  # json_integer, 1-100 (RAMP_RATE)
    ST: Final = "St"  # json_boolean, True/False (POWER state)

    # ZONE PROPERTY_LIST keys
    DEVICE_TYPE: Final = "DeviceType"  # json_string, DIMMER/, reported only
    POWER: Final = "Power"  # json_boolean, True/False
    POWER_LEVEL: Final = "PowerLevel"  # json_integer, 1-100
    RAMP_RATE: Final = "RampRate"  # json_integer, 1-100

    # ZONE PROPERTY_LIST, DEVICE_TYPE values
    DIMMER: Final = "Dimmer"
    SWITCH: Final = "Switch"

    # SERVICE values
    CREATE_SCENE: Final = "CreateScene"
    DELETE_SCENE: Final = "DeleteScene"
    DELETE_ZONE: Final = "DeleteZone"
    LIST_SCENES: Final = "ListScenes"
    LIST_ZONES: Final = "ListZones"
    REPORT_SCENE_PROPERTIES: Final = "ReportSceneProperties"
    REPORT_SYSTEM_PROPERTIES: Final = "ReportSystemProperties"
    REPORT_ZONE_PROPERTIES: Final = "ReportZoneProperties"
    RUN_SCENE: Final = "RunScene"
    SET_SCENE_PROPERTIES: Final = "SetSceneProperties"
    SET_SYSTEM_PROPERTIES: Final = "SetSystemProperties"
    SET_ZONE_PROPERTIES: Final = "SetZoneProperties"
    TRIGGER_RAMP_COMMAND: Final = "TriggerRampCommand"
    TRIGGER_RAMP_ALL_COMMAND: Final = "TriggerRampAllCommand"

    # SET_SYSTEM_PROPERTIES PROPERTY_LIST keys
    ADD_A_LIGHT: Final = "AddALight"  # json_boolean, True to enable
    TIME_ZONE: Final = "TimeZone"  # json_integer, seconds offset from GMT
    EFFECTIVE_TIME_ZONE: Final = "EffectiveTimeZone"  # json_integer, seconds offset from GMT including DST
    DAYLIGHT_SAVING_TIME: Final = (
        "DaylightSavingTime"  # json_boolean, True for DST
    )
    LOCATION_INFO: Final = "LocationInfo"  # json_string, LOCATION description
    LOCATION: Final = "Location"  # json_object, LAT and LONG
    CONFIGURED: Final = (
        "Configured"  # json_boolean, True to say LCM configured
    )
    LAT: Final = "Lat"  # json_object, latitude in DEG, MIN, SEC
    LONG: Final = "Long"  # json_object longitude in DEG, MIN, SEC
    DEG: Final = "Deg"  # json_integer, degrees
    MIN: Final = "Min"  # json_integer, minutes
    SEC: Final = "Sec"  # json_integer, seconds

    # SET_SYSTEM_PROPERTIES PROPERTY_LIST security keys
    KEYS: Final = "Keys"

    def wrap(self, _id, message: MutableMapping[str, Any]) -> bytes:
        """Wrap a composed message, with _id, in a frame."""
        message[self._ID] = _id
        return json.dumps(message).encode() + b"\x00"

    def compose_delete_scene(self, sid: int):
        """Compose a DELETE_SCENE message."""
        return {self.SERVICE: self.DELETE_SCENE, self.SID: sid}

    def compose_delete_zone(self, zid: int):
        """Compose a DELETE_ZONE message."""
        return {self.SERVICE: self.DELETE_ZONE, self.ZID: zid}

    def compose_list_scenes(self):
        """Compose a LIST_SCENES message."""
        return {self.SERVICE: self.LIST_SCENES}

    def compose_list_zones(self):
        """Compose a LIST_ZONES message."""
        return {self.SERVICE: self.LIST_ZONES}

    def compose_report_scene_properties(self, sid: int):
        """Compose a REPORT_SCENE_PROPERTIES message."""
        return {self.SERVICE: self.REPORT_SCENE_PROPERTIES, self.SID: sid}

    def compose_report_system_properties(self):
        """Compose a REPORT_SYSTEM_PROPERTIES message."""
        return {self.SERVICE: self.REPORT_SYSTEM_PROPERTIES}

    def compose_report_zone_properties(self, zid: int):
        """Compose a REPORT_ZONE_PROPERTIES message."""
        return {self.SERVICE: self.REPORT_ZONE_PROPERTIES, self.ZID: zid}

    def compose_set_zone_properties(  # pylint: disable=too-many-arguments
        self,
        zid: int,
        name: str = None,
        power: bool = None,
        power_level: int = None,
        ramp_rate: int = None,
    ):
        """Compose a SET_ZONE_PROPERTIES message."""
        property_list: dict[str, Any] = {}
        if name is not None:
            property_list[self.NAME] = name
        if power is not None:
            property_list[self.POWER] = power
        if power_level is not None:
            property_list[self.POWER_LEVEL] = power_level
        if ramp_rate is not None:
            property_list[self.RAMP_RATE] = ramp_rate
        return {
            self.SERVICE: self.SET_ZONE_PROPERTIES,
            self.ZID: zid,
            self.PROPERTY_LIST: property_list,
        }

    def compose_set_system_properties(
        self,
        add_a_light: bool = None,
        time_zone: int = None,
        effective_time_zone: int = None,
        daylight_saving_time: bool = None,
        location_info: str = None,
        location: Mapping = None,
        configured: bool = None,
    ):
        """Compose a SET_SYSTEM_PROPERTIES message."""
        property_list: dict[str, Any] = {}
        if add_a_light is not None:
            property_list[self.ADD_A_LIGHT] = add_a_light
        if time_zone is not None:
            property_list[self.TIME_ZONE] = time_zone
        if effective_time_zone is not None:
            property_list[self.EFFECTIVE_TIME_ZONE] = effective_time_zone
        if daylight_saving_time is not None:
            property_list[self.DAYLIGHT_SAVING_TIME] = daylight_saving_time
        if location_info is not None:
            property_list[self.LOCATION_INFO] = location_info
        if location is not None:
            property_list[self.LOCATION] = location
        if configured is not None:
            property_list[self.CONFIGURED] = configured
        return {
            self.SERVICE: self.SET_SYSTEM_PROPERTIES,
            self.PROPERTY_LIST: property_list,
        }

    @staticmethod
    def _encrypt(key: bytes, data: bytes) -> bytes:
        cipher = Cipher(algorithms.AES(key), modes.ECB())
        encryptor = cipher.encryptor()
        return encryptor.update(data) + encryptor.finalize()

    def compose_keys(self, old: bytes, new: bytes):
        """Compose a message to change key from old to new."""
        return {
            self.SERVICE: self.SET_SYSTEM_PROPERTIES,
            self.PROPERTY_LIST: {
                self.KEYS: "".join(
                    [self._encrypt(old, key).hex() for key in (old, new)]
                )
            },
        }


class _Sender(Composer):
    def __init__(self):
        self._id = 0  # id of last send
        self._writer: asyncio.StreamWriter = None

    async def send(self, message: MutableMapping[str, Any]):
        """Send a composed message with the next ID."""
        writer = self._writer
        if writer is None:
            _logger.warning("\t! %s", message)
        else:
            self._id += 1
            writer.write(self.wrap(self._id, message))
            await writer.drain()
            _logger.debug("\t< %s", message)


class _Inner:  # pylint: disable=too-few-public-methods
    """An _Inner instance remembers its outer instance."""

    def __init__(self, outer):
        self._outer = outer

    def outer(self):
        """Get private _outer attribute."""
        return self._outer


class Receiver(_Sender):
    """A Receiver's messages are handled by an abstract receive method."""

    # default constructor values
    READ_TIMEOUT: Final = 20.0  # expect ping every 5 seconds

    class StatusError(ValueError):
        """StatusError whose args are derived from a message.

        Returns (error: bool, code: int = 0, text: str = None)
        where error is True if STATUS is not STATUS_SUCCESS,
        code is ERROR_CODE value (or 0)
        and text is ERROR_TEXT value (or None)."""

        # message keys
        ERROR_TEXT: Final = "ErrorText"
        ERROR_CODE: Final = "ErrorCode"
        STATUS: Final = "Status"

        # STATUS values
        STATUS_SUCCESS: Final = "Success"
        STATUS_ERROR: Final = "Error"

        def __init__(self, message: Mapping):
            super().__init__(
                message.get(self.STATUS, self.STATUS_ERROR)
                != self.STATUS_SUCCESS,
                int(message.get(self.ERROR_CODE, "0")),
                message.get(self.ERROR_TEXT, None),
            )

        def __bool__(self):
            return bool(self.args[0])

        def raise_if(self):
            """raise self if bool(self)."""
            if bool(self):
                raise self

    def __init__(self, read_timeout: float = READ_TIMEOUT):
        super().__init__()
        self._reader: asyncio.StreamReader = None
        self._read_timeout = read_timeout
        self._frames = self._Frames(self)

    @abc.abstractmethod
    async def receive(self, message: Mapping):
        """Receive a message."""

    class _Frames(_Inner, collections.abc.AsyncIterator):
        def __aiter__(self):
            return self

        async def __anext__(self):
            # return null terminated frame, without the terminator
            return (
                await asyncio.wait_for(
                    self.outer()._reader.readuntil(b"\x00"),
                    self.outer()._read_timeout,
                )
            )[:-1]

    async def unwrap(self, frame: bytes):
        """Unwrap message in frame and receive it."""
        try:
            message = json.loads(frame)
        except json.JSONDecodeError as error:
            _logger.warning("except json.JSONDecodeError: %s %s", error, frame)
        else:
            await self.receive(message)

    async def session(self):
        """Iterate over read frames forever."""
        async for frame in self._frames:
            _logger.debug("\t\t> %s", frame.decode())
            await self.unwrap(frame)


class _EventEmitter:
    """_EventEmitter pattern implementation."""

    class _Once(_Inner):  # pylint: disable=too-few-public-methods
        """_Once (_Inner class of _EventEmitter) forwards an emission once."""

        NOTHING: Final = object()  # do not forward an event of NOTHING

        async def _forward(self, *event):
            self.outer().off(self._name, self._forward)
            if len(event) != 1 or event[0] is not self.NOTHING:
                await self._handler(*event)

        def __init__(
            self, outer, name: str, handler: collections.abc.Awaitable
        ):
            super().__init__(outer)
            self._name = name
            self._handler = handler
            self.outer().on(self._name, self._forward)

    def __init__(self):
        self._handlers = {}

    def on(
        self, name: str, handler: collections.abc.Awaitable
    ):  # pylint: disable=invalid-name
        """Register the handler for events with this name."""
        if name not in self._handlers:
            self._handlers[name] = [handler]
        else:
            self._handlers[name].append(handler)
        return self

    def off(self, name: str, handler: collections.abc.Awaitable):
        """Unregister the handler for events with this name."""
        if name not in self._handlers:
            raise ValueError(name)
        handlers = self._handlers[name]
        handlers.remove(handler)  # may raise ValueError
        if len(handlers) == 0:
            del self._handlers[name]
        return self

    def once(self, name: str, handler: collections.abc.Awaitable):
        """Register the handler for one event with this name."""
        self._Once(self, name, handler)
        return self

    async def _emit(self, name: str, *event):
        """Emit *event to all handlers for name."""
        if name in self._handlers:
            # iterate over a copy so that a handler may change the handlers
            handlers = self._handlers[name].copy()
            for handler in handlers:
                await handler(*event)
        return self


class Emitter(Receiver, _EventEmitter):
    """Emitter is a Receiver and an _EventEmitter of received messages."""

    # events emitted with message
    EVENT_BROADCAST: Final = f"{Receiver._ID}:0"
    EVENT_DELETE_ZONE: Final = f"{Receiver.SERVICE}:{Receiver.DELETE_ZONE}"
    EVENT_LIST_SCENES: Final = f"{Receiver.SERVICE}:{Receiver.LIST_SCENES}"
    EVENT_LIST_ZONES: Final = f"{Receiver.SERVICE}:{Receiver.LIST_ZONES}"
    EVENT_PING: Final = f"{Receiver.SERVICE}:ping"
    EVENT_REPORT_SCENE_PROPERTIES: Final = (
        f"{Receiver.SERVICE}:{Receiver.REPORT_SCENE_PROPERTIES}"
    )
    EVENT_REPORT_SYSTEM_PROPERTIES: Final = (
        f"{Receiver.SERVICE}:{Receiver.REPORT_SYSTEM_PROPERTIES}"
    )
    EVENT_REPORT_ZONE_PROPERTIES: Final = (
        f"{Receiver.SERVICE}:{Receiver.REPORT_ZONE_PROPERTIES}"
    )
    EVENT_RUN_SCENE: Final = f"{Receiver.SERVICE}:{Receiver.RUN_SCENE}"
    EVENT_SET_SCENE_PROPERTIES: Final = (
        f"{Receiver.SERVICE}:{Receiver.SET_SCENE_PROPERTIES}"
    )
    EVENT_SET_SYSTEM_PROPERTIES: Final = (
        f"{Receiver.SERVICE}:{Receiver.SET_SYSTEM_PROPERTIES}"
    )
    EVENT_SET_ZONE_PROPERTIES: Final = (
        f"{Receiver.SERVICE}:{Receiver.SET_ZONE_PROPERTIES}"
    )
    EVENT_SCENE_CREATED: Final = f"{Receiver.SERVICE}:SceneCreated"
    EVENT_SCENE_DELETED: Final = f"{Receiver.SERVICE}:SceneDeleted"
    EVENT_SCENE_PROPERTIES_CHANGED: Final = (
        f"{Receiver.SERVICE}:ScenePropertiesChanged"
    )
    EVENT_SYSTEM_PROPERTIES_CHANGED: Final = (
        f"{Receiver.SERVICE}:SystemPropertiesChanged"
    )
    EVENT_TRIGGER_RAMP_COMMAND: Final = (
        f"{Receiver.SERVICE}:{Receiver.TRIGGER_RAMP_COMMAND}"
    )
    EVENT_TRIGGER_RAMP_ALL_COMMAND: Final = (
        f"{Receiver.SERVICE}:{Receiver.TRIGGER_RAMP_ALL_COMMAND}"
    )
    EVENT_ZONE_ADDED: Final = f"{Receiver.SERVICE}:ZoneAdded"
    EVENT_ZONE_DELETED: Final = f"{Receiver.SERVICE}:ZoneDeleted"
    EVENT_ZONE_PROPERTIES_CHANGED: Final = (
        f"{Receiver.SERVICE}:ZonePropertiesChanged"
    )

    async def receive(self, message: Mapping):
        if self._ID in message:
            _id = message[self._ID]
            if _id != 0:
                # emit what we received (NOTHING) until caught up.
                # such will be acknowledged but not forwarded by Once.
                while self._emit_id < _id:
                    await self._emit(f"ID:{self._emit_id}", self._Once.NOTHING)
                    self._emit_id += 1
            await self._emit(f"ID:{_id}", message)
        if self.SERVICE in message:
            service = message[self.SERVICE]
            await self._emit(f"{self.SERVICE}:{service}", message)
            if self.ZID in message:
                zid = message[self.ZID]
                await self._emit(f"{self.SERVICE}:{service}:{zid}", message)

    async def handle_send(
        self, handler: collections.abc.Awaitable, message: MutableMapping
    ):
        """Handle the response from the message we will send."""
        self.once(f"{self._ID}:{self._id + 1}", handler)
        await self.send(message)

    def __init__(self, read_timeout: float = Receiver.READ_TIMEOUT):
        Receiver.__init__(self, read_timeout)
        _EventEmitter.__init__(self)
        self._emit_id = 1  # id of next emit


class Authenticator(Emitter):  # pylint: disable=too-few-public-methods
    """An Authenticator session runs for the first/authentication phase only.

    This phase will either end by exception (Authenticator.Error)
    or the MAC address of the unit that we successfully authenticated with.
    """

    # authenticated events emitted
    EVENT_AUTHENTICATED: Final = "authenticated"
    EVENT_UNAUTHENTICATED: Final = "unauthenticated"

    # Security message prefixes
    SECURITY_MAC: Final = b'{"MAC":'
    SECURITY_HELLO: Final = b"Hello V1 "
    SECURITY_HELLO_INVALID: Final = b"[INVALID]"
    SECURITY_HELLO_OK: Final = b"[OK]"
    SECURITY_SETKEY: Final = b"[SETKEY]"

    # SECURITY_MAC and SECURITY_SETKEY key
    MAC: Final = "MAC"

    def __init__(
        self,
        key: bytes = None,
        read_timeout: float = Receiver.READ_TIMEOUT,
    ):
        super().__init__(read_timeout)
        self._key: bytes = key
        self._address = None
        self._authenticated: bool = False

    class Error(ValueError):
        """Authentication error."""

    class _Result(asyncio.CancelledError):
        """Chained from an Error if there was one."""

    async def _send_challenge_response(self, key: bytes, challenge: bytes):
        if key is None:
            raise self._Result() from self.Error("authentication required")
        message = self._encrypt(key, challenge).hex()
        writer = self._writer
        writer.write(message.encode())
        await writer.drain()
        _logger.debug("\t< %s", message)

    async def _receive_security_setkey(self):
        # } terminated json encoding
        frame = await asyncio.wait_for(
            self._reader.readuntil(b"}"), self._read_timeout
        )
        _logger.debug("\t\t> %s", frame.decode())
        try:
            message = json.loads(frame)
        except json.JSONDecodeError as error:
            _logger.warning("except json.JSONDecodeError: %s %s", error, frame)
        else:
            self._address = message[self.MAC]

            async def handle(message: Mapping):
                try:
                    self.StatusError(message).raise_if()
                except self.StatusError as error:
                    raise self._Result() from error
                else:
                    raise self._Result()

            if self._key is None:
                raise self._Result() from self.Error("authentication required")
            await self.handle_send(
                handle, self.compose_keys(hash_password(b""), self._key)
            )

    async def _receive_security_hello(self):
        # space terminated challenge phrase
        challenge = (
            await asyncio.wait_for(
                self._reader.readuntil(b" "), self._read_timeout
            )
        )[:-1]
        _logger.debug("\t\t>\t%s", challenge.decode())
        # 12 byte MAC address
        self._address = (
            await asyncio.wait_for(
                self._reader.readexactly(12), self._read_timeout
            )
        ).decode()
        _logger.debug("\t\t>\t%s", self._address)
        await self._send_challenge_response(
            self._key, bytes.fromhex(challenge.decode())
        )

    def _receive_security_hello_ok(self):
        raise self._Result()

    def _receive_security_hello_invalid(self):
        raise self._Result() from self.Error("Invalid")

    def _receive_security_mac(self, message):
        self._address = message[self.MAC]
        raise self._Result()

    async def _unwrap_security_mac(self, frame):
        try:
            message = json.loads(frame)
            self._receive_security_mac(message)
        except json.JSONDecodeError:
            # may be concatenated (improperly, for JSON) with another(s?).
            # rewrite/retry it as an array of frames
            frames = b"[" + frame.replace(b"}{", b"},{") + b"]"
            try:
                messages = json.loads(frames)
            except json.JSONDecodeError as error:
                _logger.warning(
                    "except json.JSONDecodeError: %s %s", error, frames
                )
            else:
                mac, *others = messages
                try:
                    self._receive_security_mac(mac)
                finally:
                    for message in others:
                        await self.receive(message)

    async def unwrap(self, frame: bytes):
        if frame.startswith(self.SECURITY_MAC):
            await self._unwrap_security_mac(frame)
        elif frame.startswith(self.SECURITY_SETKEY):
            await self._receive_security_setkey()
        elif frame.startswith(self.SECURITY_HELLO):
            await self._receive_security_hello()
        elif frame.startswith(self.SECURITY_HELLO_OK):
            await self._receive_security_hello_ok()
        elif frame.startswith(self.SECURITY_HELLO_INVALID):
            self._receive_security_hello_invalid()
        else:
            await super().unwrap(frame)

    @property
    def authenticated(self):
        """Return True if session successfully authenticated."""
        return self._authenticated

    async def session(self):
        try:
            await super().session()
        except self._Result as root:
            address = self._address
            self._address = None
            if root.__cause__ is None:
                self._authenticated = True
                await self._emit(self.EVENT_AUTHENTICATED, address)
                return address
            self._authenticated = False
            await self._emit(self.EVENT_UNAUTHENTICATED)
            raise root.__cause__ from None


class _ConnectionContext(contextlib.AbstractAsyncContextManager):
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._writer = None

    async def __aenter__(self):
        reader, self._writer = await asyncio.open_connection(
            self._host, self._port
        )
        return (reader, self._writer)

    async def __aexit__(self, et, ev, tb):
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except OSError:
            pass


class Connector(Authenticator):
    """A Connector is an Authenticator that loops over connections/sessions."""

    # connected events emitted
    EVENT_CONNECTED: Final = "connected"
    EVENT_DISCONNECTED: Final = "disconnected"

    # default arguments
    HOST: Final = "LCM1.local"
    PORT: Final = 2112
    LOOP_TIMEOUT: Final = 2 ** 8

    def __init__(  # pylint: disable=too-many-arguments
        self,
        host: str = HOST,
        port: int = PORT,
        loop_timeout: float = LOOP_TIMEOUT,
        key: bytes = None,
        read_timeout: float = Receiver.READ_TIMEOUT,
    ):
        super().__init__(key, read_timeout)
        self._host = host
        self._port = port
        self._loop_timeout = loop_timeout
        self._task = None

    def host(self):
        return self._host

    async def cancel(self):
        """Cancel the task running loop()."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @property
    def connected(self):
        """Return true if currently connected."""
        return self._writer is not None

    async def loop(self):
        """Return the result of the first successful connection/session.

        If loop_timeout < 0, raise OSError if (and why) connection could not be made;
        otherwise, reconnect after exponential backoff (up to loop_timeout seconds)
        before trying again."""
        self._task = asyncio.current_task()
        count = 0
        try:
            while True:
                try:
                    async with _ConnectionContext(
                        self._host, self._port
                    ) as connection:
                        # connection success, will be closed with context exit
                        count = 0
                        self._reader, self._writer = connection
                        await self._emit(self.EVENT_CONNECTED)
                        try:
                            return await self.session()
                        except EOFError:
                            _logger.warning("EOFError")
                        except OSError as error:
                            _logger.warning("OSError %s", error)
                        except asyncio.TimeoutError:
                            _logger.warning("asyncio.TimeoutError")
                        finally:
                            self._reader, self._writer = None, None
                            await self._emit(self.EVENT_DISCONNECTED)
                except OSError as error:
                    # connection error
                    if self._loop_timeout < 0:
                        raise
                    _logger.warning("OSError %s", error)
                    # reconnect after exponential backoff
                    await asyncio.sleep(min(2 ** count, self._loop_timeout))
                    count += 1
        finally:
            self._task = None


class Hub(Connector):
    """Each Hub session acts as an Authenticator then Emitter."""

    async def session(self):
        await Authenticator.session(self)
        await Emitter.session(self)
