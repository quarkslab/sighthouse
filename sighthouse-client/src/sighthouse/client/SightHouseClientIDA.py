import ida_kernwin
import ida_nalt
import ida_loader
import ida_funcs
import ida_ida
import ida_diskio
import idaapi
import ida_idaapi
import ida_idp
import ida_segment

# TODO handle different version IDA8/IDA9 ida_nalt.get_initial_ida_version()

from typing import Iterator, List, Tuple

idaapi.require("sighthouse")

from sighthouse.client.SightHouseClient import (
    SightHouseAnalysis,
    Section,
    Function,
    get_hash,
)


class LoggingIDASighthouse(object):

    def __init__(self) -> None:
        """Initialize logging class"""
        # TOD0

    def error(self, message: str):
        """Show an error message

        Args:
            message (str): The message to show
        """
        # TODO
        ida_kernwin.warning(message)

    def warning(self, message: str):
        """Show an warning message

        Args:
            message (str): The message to show
        """
        # TODO
        ida_kernwin.warning(message)

    def info(self, message: str):
        """Show an info message

        Args:
            message (str): The message to show
        """
        # TODO
        ida_kernwin.msg(message)


class SightHouseIDAPlugin(ida_idaapi.plugin_t):
    flags = ida_idaapi.PLUGIN_UNL | ida_idaapi.PLUGIN_MULTI
    comment = "SightHouse plugin for IDA Pro"
    help = "no help for ida user"
    wanted_name = "SightHouseClient"
    wanted_hotkey = "Ctrl-Shift-A"

    def init(self):
        return SightHouseIDAPluginMod()


class ConfForm(ida_kernwin.Form):

    def __init__(self):
        """
        Display a Pop-Up
        """
        RENAME_FORM_TEXT = r"""BUTTON YES* Launch
BUTTON CANCEL* Cancel


        Server configuration:
            <Url: {url}>
            <Username: {username}>
            <Password: {password}>
            <Verify host: {verify_host_enable}>{verify_host}>
            <Force submission: {force_submission_enable}>{force_submission}>
            <Bob Ross: {bob_ross_enable}>{bob_ross}>
"""
        # self.invert = False
        self.save_cache = True
        self.show_dialog = True
        rename_form_dict = {
            "url": ida_kernwin.Form.StringInput(),
            "username": ida_kernwin.Form.StringInput(),
            "password": ida_kernwin.Form.StringInput(),
            "verify_host": ida_kernwin.Form.ChkGroupControl(("verify_host_enable",)),
            "force_submission": ida_kernwin.Form.ChkGroupControl(
                ("force_submission_enable",)
            ),
            "bob_ross": ida_kernwin.Form.ChkGroupControl(("bob_ross_enable",)),
        }
        ida_kernwin.Form.__init__(self, RENAME_FORM_TEXT, rename_form_dict)


class SightHouseIDAPluginMod(ida_idaapi.plugmod_t):
    def __del__(self):
        pass

    def run(self, arg):
        print(
            f">>> SightHouseIDAPluginMod.run() is invoked with argument value: {arg}."
        )
        form = ConfForm()
        form.Compile()
        ok = form.Execute()
        if ok == ida_kernwin.ASKBTN_YES:
            url = form.url.value
            username = form.username.value
            password = form.password.value
            verify_host = form.verify_host_enable.checked
            force_submission = form.force_submission_enable.checked
            bob_ross = form.bob_ross_enable.checked
            s = SightHouseIDAAnalysis(
                url,
                username,
                password,
                verify_host,
                force_submission,
                options={
                    "BobRoss": bob_ross,
                },
            )
            s.run()
        else:
            print("User canceled the dialog.")
        form.Free()


class SightHouseIDAAnalysis(SightHouseAnalysis):

    proc_names = {
        ida_idp.PLFM_386: "x86",
        ida_idp.PLFM_I860: "x86",
        ida_idp.PLFM_8051: "8051",
        ida_idp.PLFM_TMS: "Not Supported",
        ida_idp.PLFM_6502: "6502",
        ida_idp.PLFM_PDP: "Not Supported",
        ida_idp.PLFM_68K: "68000",
        ida_idp.PLFM_JAVA: "JVM",
        ida_idp.PLFM_6800: "Not Supported",
        ida_idp.PLFM_ST7: "Not Supported",
        ida_idp.PLFM_MC6812: "Not Supported",
        ida_idp.PLFM_MIPS: "MIPS",
        ida_idp.PLFM_ARM: "ARM",
        ida_idp.PLFM_TMSC6: "Not Supported",
        ida_idp.PLFM_PPC: "PowerPC",
        ida_idp.PLFM_80196: "Not Supported",
        ida_idp.PLFM_Z8: "Not Supported",
        ida_idp.PLFM_SH: "SuperH",
        ida_idp.PLFM_NET: "Not Supported",
        ida_idp.PLFM_AVR: "avr32",
        ida_idp.PLFM_H8: "Not Supported",
        ida_idp.PLFM_PIC: "PIC-24",
        ida_idp.PLFM_SPARC: "sparc",
        ida_idp.PLFM_ALPHA: "Not Supported",
        ida_idp.PLFM_HPPA: "Not Supported",
        ida_idp.PLFM_H8500: "Not Supported",
        ida_idp.PLFM_TRICORE: "tricore",
        ida_idp.PLFM_DSP56K: "Not Supported",
        ida_idp.PLFM_C166: "Not Supported",
        ida_idp.PLFM_ST20: "Not Supported",
        ida_idp.PLFM_IA64: "x86",
        ida_idp.PLFM_I960: "Not Supported",
        ida_idp.PLFM_F2MC: "Not Supported",
        ida_idp.PLFM_TMS320C54: "Not Supported",
        ida_idp.PLFM_TMS320C55: "Not Supported",
        ida_idp.PLFM_TRIMEDIA: "Not Supported",
        ida_idp.PLFM_M32R: "Not Supported",
        ida_idp.PLFM_NEC_78K0: "Not Supported",
        ida_idp.PLFM_NEC_78K0S: "Not Supported",
        ida_idp.PLFM_M740: "Not Supported",
        ida_idp.PLFM_M7700: "Not Supported",
        ida_idp.PLFM_ST9: "Not Supported",
        ida_idp.PLFM_FR: "Not Supported",
        ida_idp.PLFM_MC6816: "Not Supported",
        ida_idp.PLFM_M7900: "Not Supported",
        ida_idp.PLFM_TMS320C3: "Not Supported",
        ida_idp.PLFM_KR1878: "Not Supported",
        ida_idp.PLFM_AD218X: "Not Supported",
        ida_idp.PLFM_OAKDSP: "Not Supported",
        ida_idp.PLFM_TLCS900: "Not Supported",
        ida_idp.PLFM_C39: "Not Supported",
        ida_idp.PLFM_CR16: "Not Supported",
        ida_idp.PLFM_MN102L00: "Not Supported",
        ida_idp.PLFM_TMS320C1X: "Not Supported",
        ida_idp.PLFM_NEC_V850X: "Not Supported",
        ida_idp.PLFM_SCR_ADPT: "Not Supported",
        ida_idp.PLFM_EBC: "Not Supported",
        ida_idp.PLFM_MSP430: "Not Supported",
        ida_idp.PLFM_SPU: "Not Supported",
        ida_idp.PLFM_DALVIK: "Dalvik",
        ida_idp.PLFM_65C816: "Not Supported",
        ida_idp.PLFM_M16C: "Not Supported",
        ida_idp.PLFM_ARC: "Not Supported",
        ida_idp.PLFM_UNSP: "Not Supported",
        ida_idp.PLFM_TMS320C28: "Not Supported",
        ida_idp.PLFM_DSP96K: "Not Supported",
        ida_idp.PLFM_SPC700: "Not Supported",
        ida_idp.PLFM_AD2106X: "Not Supported",
        ida_idp.PLFM_PIC16: "PIC-16",
        ida_idp.PLFM_S390: "Not Supported",
        ida_idp.PLFM_XTENSA: "Xtensa",
        ida_idp.PLFM_RISCV: "RISCV",
        ida_idp.PLFM_RL78: "Not Supported",
        ida_idp.PLFM_RX: "Not Supported",
        ida_idp.PLFM_WASM: "Not Supported",
    }

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        verify_host: bool = True,
        force_submission: bool = False,
        options=None,
    ) -> None:
        logger = LoggingIDASighthouse()
        super().__init__(
            username,
            password,
            url,
            logger,
            verify_host,
            force_submission,
            options=options,
        )

    def get_current_arch(self) -> None:
        """get current architecture and translate to ghidra one"""
        name_arch = self.proc_names.get(ida_idp.ph_get_id(), "Not Supported")
        version = "default"
        if name_arch == "ARM":
            version = "v8T"
        endianness = "BE"
        if ida_ida.inf_get_lflags() & ida_ida.LFLG_PC_FLAT:
            endianness = "LE"
        size_arch = "8"
        if ida_ida.inf_is_64bit():
            size_arch = "64"
        elif ida_ida.inf_is_32bit_exactly():
            size_arch = "32"
        elif ida_ida.inf_is_16bit():
            size_arch = "16"

        full_arch = f"{name_arch}:{endianness}:{size_arch}:{version}"

        return full_arch

    def update_progress(self, message: str) -> None:
        """show an update progress

        Args:
            message (str): message to show
        """
        print(message)

    @staticmethod
    def get_segments(skip_header_segments=False) -> Iterator[idaapi.segment_t]:
        """get list of segments (sections) in the binary image

        args:
            skip_header_segments: IDA may load header segments - skip if set
        """
        for n in range(idaapi.get_segm_qty()):
            seg = idaapi.getnseg(n)
            if seg and not (skip_header_segments and seg.is_header_segm()):
                yield seg

    def get_program_name(self) -> str:
        """Get program name

        Returns:
            str: the program name
        """
        return idaapi.get_root_filename()

    def get_sections(self) -> List[Section]:
        """Get sections

        Returns:
            List[Section]: list sections
        """
        res = []
        for seg in SightHouseIDAAnalysis.get_segments(skip_header_segments=True):
            perms = (
                "R" if seg.perm & idaapi.SEGPERM_READ == idaapi.SEGPERM_READ else " "
            )
            perms += (
                "W" if seg.perm & idaapi.SEGPERM_WRITE == idaapi.SEGPERM_WRITE else " "
            )
            perms += (
                "X" if seg.perm & idaapi.SEGPERM_EXEC == idaapi.SEGPERM_EXEC else " "
            )
            if (
                seg.type & idaapi.SEG_CODE == idaapi.SEG_CODE
                or seg.type & idaapi.SEG_DATA == idaapi.SEG_DATA
            ):
                res.append(
                    Section(
                        ida_segment.get_segm_name(seg),
                        int(seg.start_ea),
                        int(seg.end_ea),
                        int(idaapi.get_fileregion_offset(seg.start_ea)),
                        perms,
                        "",
                    )
                )
            else:
                res.append(
                    Section(
                        ida_segment.get_segm_name(seg),
                        int(seg.start_ea),
                        int(seg.end_ea),
                        -1,
                        perms,
                        "",
                    )
                )

        return res

    def get_functions(self, section: Section) -> List[Function]:
        """get functions

        Args:
            section (Section): section

        Returns:
            List[Function]: list of function inside the section
        """
        self._logger.warning("Architecture details such as Thumb are not implemented")

        ret_funcs = []
        func_ea = ida_funcs.get_next_func(section.start)
        while (
            not func_ea is None
            and func_ea.start_ea != idaapi.BADADDR
            and func_ea.end_ea < section.end
        ):
            ret_funcs.append(
                Function(
                    ida_funcs.get_func_name(func_ea.start_ea),
                    func_ea.start_ea - section.start,
                )
            )
            func_ea = ida_funcs.get_next_func(func_ea.start_ea)
        return ret_funcs

    def get_hash_program(self) -> str:
        """get hash of program

        Returns:
            str: sha256 string
        """
        # return idaapi.retrieve_input_file_sha256()
        return get_hash(self.get_current_binary())

    def get_current_binary(self) -> bytes:
        """Retrieve the current binaries in bytes

        Returns:
            bytes: the content in bytes of the current binaries
        """
        pathname = idaapi.get_input_file_path()
        try:
            # Open the file and read its contents
            with open(pathname, "rb") as f:
                return f.read()
        except Exception as e:
            self._logger.error(str(e))
        return b""

    def add_tag(self, address: int, tag: str, message: str) -> None:
        """Add a tag on the SRE

        Args:
            address (int): address where put the tag
            tag (str): tag of message
            message (str): message to show
        """
        ida_funcs.set_func_cmt(ida_funcs.get_func(address), f"{tag}: {message}", True)

    def term(self):
        pass


def PLUGIN_ENTRY():
    return SightHouseIDAPlugin()


if __name__ == "__main__":
    # example
    analyzer = SightHouseIDAAnalysis(
        "http://localhost:6669", "toto", "83ef32ec6adb69b19acb5c37eda8b2e3"
    )
    analyzer.run()
