"""
:file:      tcpip_tcp_com_if.py
:date:      13.05.2021
:brief:     TCP communication interface
:author:    R. Mueller
"""
import socket
import time
import enum
import threading
import select
from collections import deque
from typing import Union, Optional

from tmtccmd.utility.logger import get_console_logger
from tmtccmd.config.definitions import CoreModeList
from tmtccmd.com_if.com_interface_base import CommunicationInterface
from tmtccmd.tm.definitions import TelemetryListT
from tmtccmd.utility.tmtc_printer import TmTcPrinter
from tmtccmd.config.definitions import EthernetAddressT
from tmtccmd.utility.conf_util import acquire_timeout
from tmtccmd.ccsds.spacepacket import parse_space_packets

LOGGER = get_console_logger()

TCP_RECV_WIRETAPPING_ENABLED = False
TCP_SEND_WIRETAPPING_ENABLED = False


class TcpCommunicationType(enum.Enum):
    """Parse for space packets in the TCP stream, using the space packet header"""
    SPACE_PACKETS = 0


# pylint: disable=abstract-method
# pylint: disable=arguments-differ
# pylint: disable=too-many-arguments
class TcpIpTcpComIF(CommunicationInterface):
    """Communication interface for TCP communication."""
    DEFAULT_LOCK_TIMEOUT = 0.4
    TM_LOOP_DELAY = 0.2

    def __init__(
            self, com_if_key: str, com_type: TcpCommunicationType, space_packet_id: int,
            tm_polling_freqency: float, tm_timeout: float, tc_timeout_factor: float,
            send_address: EthernetAddressT, max_recv_size: int,
            max_packets_stored: int = 50,
            tmtc_printer: Union[None, TmTcPrinter] = None,
            init_mode: int = CoreModeList.LISTENER_MODE):
        """Initialize a communication interface to send and receive TMTC via TCP
        :param com_if_key:
        :param com_type:                Communication Type. By default, it is assumed that
                                        space packets are sent via TCP
        :param space_packet_id:         16 bit packet header for space packet headers. It is used
                                        to detect the start of a header.
        :param tm_polling_freqency:     Polling frequency in seconds
        :param tm_timeout:              Timeout in seconds
        :param tmtc_printer: Printer instance, can be passed optionally to allow packet debugging
        """
        super().__init__(com_if_key=com_if_key, tmtc_printer=tmtc_printer)
        self.tm_timeout = tm_timeout
        self.com_type = com_type
        self.space_packet_id = space_packet_id
        self.tc_timeout_factor = tc_timeout_factor
        self.tm_polling_frequency = tm_polling_freqency
        self.send_address = send_address
        self.max_recv_size = max_recv_size
        self.max_packets_stored = max_packets_stored
        self.init_mode = init_mode

        self.__tcp_socket: Optional[socket.socket] = None
        self.__last_connection_time = 0
        self.__tm_thread_kill_signal = threading.Event()
        # Separate thread to request TM packets periodically if no TCs are being sent
        self.__tcp_conn_thread = threading.Thread(target=self.__tcp_tm_client, daemon=True)
        self.__tm_queue = deque()
        self.__analysis_queue = deque()
        # Only allow one connection to OBSW at a time for now by using this lock
        # self.__socket_lock = threading.Lock()
        self.__queue_lock = threading.Lock()

    def __del__(self):
        try:
            self.close()
        except IOError:
            LOGGER.warning("Could not close UDP communication interface!")

    def initialize(self, args: any = None) -> any:
        self.__tm_thread_kill_signal.clear()
        self.__tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__tcp_socket.connect(self.send_address)

    def open(self, args: any = None):
        self.__tcp_conn_thread.start()

    def close(self, args: any = None) -> None:
        self.__tm_thread_kill_signal.set()
        self.__tcp_conn_thread.join(self.tm_polling_frequency)
        self.__tcp_socket.shutdown(socket.SHUT_RDWR)
        self.__tcp_socket.close()

    def send(self, data: bytearray):
        try:
            # with acquire_timeout(self.__socket_lock, timeout=self.DEFAULT_LOCK_TIMEOUT) as \
            #        acquired:
            #    if not acquired:
            #        LOGGER.warning("Acquiring socket lock failed!")
            #    print("hello send")
            LOGGER.debug(f"sending packet with len {len(data)}")
            self.__tcp_socket.sendto(data, self.send_address)
            # self.__tcp_socket.shutdown(socket.SHUT_WR)
            # self.__receive_tm_packets(self.__tcp_socket)
            # self.__last_connection_time = time.time()
            # tcp_socket.close()
        except ConnectionRefusedError:
            LOGGER.warning("TCP connection attempt failed..")

    def receive(self, poll_timeout: float = 0) -> TelemetryListT:
        tm_packet_list = []
        with acquire_timeout(self.__queue_lock, timeout=self.DEFAULT_LOCK_TIMEOUT) as \
                acquired:
            if not acquired:
                LOGGER.warning("Acquiring queue lock failed!")
            while self.__tm_queue:
                self.__analysis_queue.appendleft(self.__tm_queue.pop())
        # TCP is stream based, so there might be broken packets or multiple packets in one recv
        # call. We parse the space packets contained in the stream here
        if self.com_type == TcpCommunicationType.SPACE_PACKETS:
            tm_packet_list = parse_space_packets(
                analysis_queue=self.__analysis_queue, packet_id=self.space_packet_id,
                max_len=self.max_recv_size
            )
        else:
            while self.__analysis_queue:
                tm_packet_list.append(self.__analysis_queue.pop())
        return tm_packet_list

    def __tcp_tm_client(self):
        LOGGER.debug("hello")
        while True and not self.__tm_thread_kill_signal.is_set():
            # if time.time() - self.__last_connection_time >= self.tm_polling_frequency:
            try:
                LOGGER.debug("recv")
                # with acquire_timeout(self.__socket_lock, timeout=self.DEFAULT_LOCK_TIMEOUT) as \
                #        acquired:
                #    if not acquired:
                #        LOGGER.warning("Acquiring socket lock in periodic handler failed!")
                # tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # tcp_socket.connect(self.send_address)
                # tcp_socket.shutdown(socket.SHUT_WR)
                self.__receive_tm_packets()
                # self.__last_connection_time = time.time()
            except ConnectionRefusedError:
                LOGGER.warning("TCP connection attempt failed..")
                self.__last_connection_time = time.time()
            time.sleep(self.TM_LOOP_DELAY)

    def __receive_tm_packets(self):
        try:
            ready = select.select([self.__tcp_socket], [], [], 0)
            if ready[0]:
                bytes_recvd = self.__tcp_socket.recv(self.max_recv_size)
                with acquire_timeout(self.__queue_lock, timeout=self.DEFAULT_LOCK_TIMEOUT) as \
                        acquired:
                    if not acquired:
                        LOGGER.warning("Acquiring queue lock failed!")
                    if self.__tm_queue.__len__() >= self.max_packets_stored:
                        LOGGER.warning(
                            "Number of packets in TCP queue too large. "
                            "Overwriting old packets.."
                        )
                        self.__tm_queue.pop()
                    self.__tm_queue.appendleft(bytearray(bytes_recvd))
        except ConnectionResetError:
            LOGGER.exception('ConnectionResetError. TCP server might not be up')

    def data_available(self, timeout: float = 0, parameters: any = 0) -> bool:
        if self.__tm_queue:
            return True
        else:
            return False
