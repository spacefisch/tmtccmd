import argparse
import collections
import pprint
from typing import Tuple

from tmtccmd.core.definitions import CoreGlobalIds, CoreComInterfaces, CoreModeList, \
    CoreServiceList, DEBUG_MODE
from tmtccmd.defaults.com_setup import default_serial_cfg_setup, default_tcpip_udp_cfg_setup
from tmtccmd.core.globals_manager import update_global, get_global
from tmtccmd.utility.tmtcc_logger import get_logger

LOGGER = get_logger()


def default_add_globals_pre_args_parsing(gui: bool = False):
    from tmtccmd.core.globals_manager import update_global
    set_default_globals_pre_args_parsing(apid=0xef)
    if gui:
        default_tcpip_udp_cfg_setup()

    service_dict = get_core_service_dict()
    update_global(CoreGlobalIds.CURRENT_SERVICE, CoreServiceList.SERVICE_17)
    update_global(CoreGlobalIds.SERVICE_DICT, service_dict)


def default_add_globals_post_args_parsing(
        args: argparse.Namespace, custom_mode_list: collections.Iterable,
        custom_service_list: collections.Iterable, custom_com_if_list: collections.Iterable):
    """
    This function takes the argument namespace as a parameter and determines following globals
    1. Mode (-m for default arguments)
    2. Communication Interface (-c for default arguments)
    3. Service (-s for default arguments)
    4. Operation Code (-o for default arguments)
    TODO: Unit test this. It is possible to simply create namespaces programatically
          and then verify the globals
    :param args: Namespace generated by parsing command line arguments.
    :param custom_mode_list: Custom list or enum of modes to check CLI argument against
    :param custom_service_list: Custom list or enum of services to check CLI argument against
    :param custom_com_if_list: Custom list of communication interfaces to check CLI argument against
    :return:
    """

    # Determine communication interface from arguments. Must be contained in core modes list
    try:
        mode_param = args.mode
    except AttributeError:
        LOGGER.warning("Passed namespace does not contain the mode (-m) argument")
        mode_param = CoreModeList.LISTENER_MODE
    check_and_set_core_mode_arg(mode_arg=mode_param, custom_mode_int_enum=custom_mode_list)

    # Determine communication interface from arguments. Must be contained in core comIF list
    try:
        com_if_param = args.com_if
    except AttributeError:
        LOGGER.warning("Passed namespace does not contain the com_if (-c) argument")
        com_if_param = CoreComInterfaces.DUMMY
    check_and_set_core_com_if_arg(com_if_arg=com_if_param)

    display_mode_param = "long"
    if args.short_display_mode is not None:
        if args.short_display_mode:
            display_mode_param = "short"
        else:
            display_mode_param = "long"
    update_global(CoreGlobalIds.DISPLAY_MODE, display_mode_param)

    # Determine service from arguments. Must be contained in core service list
    try:
        service_param = args.service
    except AttributeError:
        LOGGER.warning("Passed namespace does not contain the service (-s) argument")
        service_param = CoreServiceList.SERVICE_17
    check_and_set_core_service_arg(
        service_arg=service_param, custom_service_list=custom_service_list
    )

    if args.op_code is None:
        op_code = 0
    else:
        op_code = str(args.op_code).lower()
    update_global(CoreGlobalIds.OP_CODE, op_code)

    try:
        check_and_set_other_args(args=args)
    except AttributeError:
        LOGGER.exception("Passed arguments are missing components.")

    # For a serial communication interface, there are some configuration values like
    # baud rate and serial port which need to be set once but are expected to stay
    # the same for a given machine. Therefore, we use a JSON file to store and extract
    # those values
    if com_if_param == CoreComInterfaces.SERIAL or com_if_param == CoreComInterfaces.QEMU_SERIAL:
        default_serial_cfg_setup(com_if=com_if_param)

    # Same as above, but for server address and server port
    if com_if_param == CoreComInterfaces.TCPIP_UDP:
        # TODO: Port and IP address can also be passed as CLI parameters.
        #      Use them here if applicable?
        default_tcpip_udp_cfg_setup()
    if DEBUG_MODE:
        print_core_globals()


def get_core_service_dict() -> dict:
    core_service_dict = dict()
    core_service_dict[CoreServiceList.SERVICE_2] = ["Service 2 Raw Commanding"]
    core_service_dict[CoreServiceList.SERVICE_3] = ["Service 3 Housekeeping"]
    core_service_dict[CoreServiceList.SERVICE_5] = ["Service 5 Event"]
    core_service_dict[CoreServiceList.SERVICE_8] = ["Service 8 Functional Commanding"]
    core_service_dict[CoreServiceList.SERVICE_9] = ["Service 9 Time"]
    core_service_dict[CoreServiceList.SERVICE_17] = ["Service 17 Test"]
    core_service_dict[CoreServiceList.SERVICE_20] = ["Service 20 Parameters"]
    core_service_dict[CoreServiceList.SERVICE_23] = ["Service 23 File Management"]
    core_service_dict[CoreServiceList.SERVICE_200] = ["Service 200 Mode Management"]
    return core_service_dict


def set_default_globals_pre_args_parsing(
        apid: int, com_if_id: int = CoreComInterfaces.TCPIP_UDP, display_mode="long",
        tm_timeout: float = 4.0, print_to_file: bool = True, tc_send_timeout_factor: float = 2.0
):
    update_global(CoreGlobalIds.APID, apid)
    update_global(CoreGlobalIds.COM_IF, com_if_id)
    update_global(CoreGlobalIds.TC_SEND_TIMEOUT_FACTOR, tc_send_timeout_factor)
    update_global(CoreGlobalIds.TM_TIMEOUT, tm_timeout)
    update_global(CoreGlobalIds.DISPLAY_MODE, display_mode)
    update_global(CoreGlobalIds.PRINT_TO_FILE, print_to_file)
    update_global(CoreGlobalIds.SERIAL_CONFIG, dict())
    update_global(CoreGlobalIds.ETHERNET_CONFIG, dict())
    pp = pprint.PrettyPrinter()
    update_global(CoreGlobalIds.PRETTY_PRINTER, pp)
    update_global(CoreGlobalIds.TM_LISTENER_HANDLE, None)
    update_global(CoreGlobalIds.COM_INTERFACE_HANDLE, None)
    update_global(CoreGlobalIds.TMTC_PRINTER_HANDLE, None)
    update_global(CoreGlobalIds.PRINT_RAW_TM, False)
    update_global(CoreGlobalIds.RESEND_TC, False)
    update_global(CoreGlobalIds.OP_CODE, "0")
    update_global(CoreGlobalIds.MODE, CoreModeList.LISTENER_MODE)


def check_args_in_enum(param: any, enumeration: collections.Iterable,
                       warning_hint: str) -> Tuple[bool, int]:
    """
    This functions checks whether the integer representation of a given parameter in
    contained within the passed collections, for example an (integer) enumeration.
    Please note that if the passed parameter has a string representation but is a digit,
    this function will attempt to check whether the integer representation is contained
    inside the passed enumeration.
    :param param:           Value to be checked
    :param enumeration:     Enumeration, for example a enum.Enum or enum.IntEnum implementation
    :param warning_hint:
    :return:
    """
    might_be_integer = False
    if param is not None:
        if isinstance(param, str):
            if param.isdigit():
                might_be_integer = True
        elif isinstance(param, int):
            pass
        else:
            LOGGER.warning(f"Passed {warning_hint} type invalid.")
            return False, 0
    else:
        LOGGER.warning(f"No {warning_hint} argument passed.")
        return False, 0
    param_list = list()
    for param in enumeration:
        if isinstance(param.value, str):
            # Make this case insensitive
            param_list.append(param.value.lower())
        else:
            param_list.append(param.value)
    if param not in param_list:
        if might_be_integer:
            if int(param) in param_list:
                return True, int(param)
        LOGGER.warning(
            f"The {warning_hint} argument is not contained in the specified enumeration."
        )
        return False, 0
    return True, param


def check_and_set_core_mode_arg(mode_arg: any, custom_mode_int_enum: collections.Iterable = None):
    """
    Checks whether the mode argument is contained inside the core mode list integer enumeration
    or a custom mode list integer which can be passed optionally.
    This function will set the single command mode as the global mode parameter if the passed mode
    is not found in either enumerations.
    :param mode_arg:
    :param custom_mode_int_enum:
    :return:
    """
    in_enum, mode_value = check_args_in_enum(
        param=mode_arg, enumeration=CoreModeList, warning_hint="mode"
    )
    if in_enum:
        update_global(CoreGlobalIds.MODE, mode_value)
        return

    mode_arg_invalid = False
    if custom_mode_int_enum is not None:
        in_enum, mode_value = check_args_in_enum(
            param=mode_arg, enumeration=custom_mode_int_enum, warning_hint="custom mode"
        )
        if not in_enum:
            mode_arg_invalid = True
    else:
        mode_arg_invalid = True

    if mode_arg_invalid:
        LOGGER.warning(f"Passed mode argument might be invalid, "
                       f"setting to {CoreModeList.SINGLE_CMD_MODE}")
        mode_value = CoreModeList.SINGLE_CMD_MODE
    update_global(CoreGlobalIds.MODE, mode_value)


def check_and_set_core_com_if_arg(com_if_arg: any, custom_com_if_list: collections.Iterable = None):
    in_enum, com_if_value = check_args_in_enum(
        param=com_if_arg, enumeration=CoreComInterfaces, warning_hint="communication interface"
    )
    if in_enum:
        update_global(CoreGlobalIds.COM_IF, com_if_value)
        return

    com_if_arg_invalid = False
    if custom_com_if_list is not None:
        in_enum, com_if_value = check_args_in_enum(
            param=com_if_arg, enumeration=custom_com_if_list,
            warning_hint="custom communication interface"
        )
        if not in_enum:
            com_if_arg_invalid = True
    else:
        com_if_arg_invalid = True

    if com_if_arg_invalid:
        LOGGER.warning(f"Passed communication interface argument might be invalid, "
                       f"setting to {CoreComInterfaces.DUMMY}")
        com_if_value = CoreComInterfaces.DUMMY
    update_global(CoreGlobalIds.COM_IF, com_if_value)


def check_and_set_core_service_arg(
        service_arg: any, custom_service_list: collections.Iterable = None
):
    in_enum, service_value = check_args_in_enum(
        param=service_arg, enumeration=CoreServiceList, warning_hint="service"
    )
    if in_enum:
        update_global(CoreGlobalIds.CURRENT_SERVICE, service_value)
        return

    service_arg_invalid = False
    if custom_service_list is not None:
        in_enum, mode_value = check_args_in_enum(
            param=service_arg, enumeration=custom_service_list, warning_hint="custom mode"
        )
        if not in_enum:
            service_arg_invalid = True
    else:
        service_arg_invalid = True

    if service_arg_invalid:
        LOGGER.warning(f"Passed service argument might be invalid, "
                       f"setting to {CoreServiceList.SERVICE_17}")
        service_value = CoreServiceList.SERVICE_17
    update_global(CoreGlobalIds.CURRENT_SERVICE, service_value)


def check_and_set_other_args(args):
    if args.listener is not None:
        update_global(CoreGlobalIds.USE_LISTENER_AFTER_OP, args.listener)
    if args.tm_timeout is not None:
        update_global(CoreGlobalIds.TM_TIMEOUT, args.tm_timeout)
    if args.print_hk is not None:
        update_global(CoreGlobalIds.PRINT_HK, args.print_hk)
    if args.print_tm is not None:
        update_global(CoreGlobalIds.PRINT_TM, args.print_tm)
    if args.raw_data_print is not None:
        update_global(CoreGlobalIds.PRINT_RAW_TM, args.raw_data_print)
    if args.print_log is not None:
        update_global(CoreGlobalIds.PRINT_TO_FILE, args.print_log)
    if args.resend_tc is not None:
        update_global(CoreGlobalIds.RESEND_TC, args.resend_tc)
    update_global(CoreGlobalIds.TC_SEND_TIMEOUT_FACTOR, 3)


def print_core_globals():
    """
    Prints an imporant set of global parameters. Can be used for debugging function
    or as an optional information output
    :return:
    """
    service_param = get_global(CoreGlobalIds.CURRENT_SERVICE)
    mode_param = get_global(CoreGlobalIds.MODE)
    com_if_param = get_global(CoreGlobalIds.COM_IF)
    print(f"Current globals | Mode(-m): {mode_param} | Service(-s): {service_param} | "
          f"ComIF(-c): {com_if_param}")
