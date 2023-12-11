from aioserial import AioSerial
import logging
from asyncio import Task, sleep, TaskGroup, create_task, run
import serial.tools.list_ports as list_ports
from InquirerPy import inquirer as inquirer
import json

logger = logging.getLogger()


class Agitator:

    port: str
    line_end = "\r\n"
    _serial: AioSerial
    _baudrate: int
    _command_queue: list[str]
    # _pending_commands = 0
    _close = False
    _tg: TaskGroup
    _listener_task: Task[None]
    _writer_task: Task[None]
    # _buffer_size = 1
    _timeout: float
    agitator_index: int
    _check_connection_responses: list[float]
    _checking_connection: bool

    def __init__(self, port: str, index: int):
        self._baudrate = 9600
        self._timeout = 0.5
        self._checking_connection = False
        self._command_queue = []
        self.agitator_index = index
        self.port = port

    async def connect(self):
        self._serial = AioSerial(
            self.port, self._baudrate, timeout=self._timeout)

        self._listener_task = create_task(self._listen())
        self._writer_task = create_task(self._send_commands())

    async def _listen(self):
        # Keep reading until either the serial port closes or we've finished sending commands and the input buffer is empty
        while self._should_keep_open():
            try:
                message = (await self._serial.readline_async()).decode().strip()
                if message:
                    logger.debug(f'Agitator Reading: "{message}"')
            except:
                pass
            await sleep(0.1)

    async def _send_commands(self):
        while self._should_keep_open():
            if len(self._command_queue):
                command = self._command_queue.pop(0)
                await self._serial.write_async(
                    f"{command}{self.line_end}".encode())
                logger.debug(f'Sending: "{command}"')
            await sleep(0)

    def _should_keep_open(self):
        keep_open = (self._serial.is_open and not
                     (self._close and len(self._command_queue) == 0))
        if (keep_open == False):
            logger.info(f"closing agitator {self.agitator_index}...")
        return keep_open

    async def start(self, rpm: int = 1000):
        cmd = {
            "controller": "AGITATOR",
            "index": 0,
            "value": rpm
        }
        self.send(json.dumps(cmd))

    async def stop(self):
        cmd = {
            "controller": "AGITATOR",
            "index": 0,
            "value": 0
        }
        self.send(json.dumps(cmd))

    async def run(self, commands: list[str]):
        for command in commands:
            self._command_queue.append(command)
        while len(self._command_queue) > 0 and not self._close:
            await sleep(0)

    def send(self, command: str):
        self._command_queue.append(command)

    async def close(self):
        if not self._close:
            self._close = True
            while not self._listener_task.done():
                await sleep(0)
            while not self._writer_task.done():
                await sleep(0)
            await sleep(self._timeout + 0.1)
            self._serial.close()


class Agitators:
    agitators: list[Agitator]
    _num_agitators = 2
    _agitator_vid = "4292"

    async def connect(self):
        available_ports = list(list_ports.comports())
        ports = [port[0]
                 for port in available_ports if self._agitator_vid in str(port.vid)]
        if len(ports) == 0:
            logger.warn(
                "Couldn't find any agitators. They might be in use or not connected")
            exit()
        if len(ports) < self._num_agitators:
            logger.warn(
                f"Only found {len(ports)} of {self._num_agitators} agitators")
            exit()

        self.agitators = [Agitator(port, i) for i, port in enumerate(ports)]
        for agitator in self.agitators:
            await agitator.connect()

    async def start(self, rpm: int = 1000):
        for agitator in self.agitators:
            await agitator.start(rpm)

    async def stop(self, rpm: int = 1000):
        for agitator in self.agitators:
            await agitator.stop()

    async def close(self):
        closing: list[Task[None]] = []
        for agitator in self.agitators:
            closing.append(create_task(agitator.close()))

        for task in closing:
            await task


async def main():
    agitators = Agitators()
    await agitators.connect()
    await agitators.start()
    await sleep(5)
    await agitators.stop()
    await agitators.close()


# run(main())
