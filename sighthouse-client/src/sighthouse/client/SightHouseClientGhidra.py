## ###
# IP: GHIDRA
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##
# Sighthouse plugin
# @category: Sighthouse
# @runtime PyGhidra

from ghidra.program.model.listing import Program
from ghidra.util import Msg
from ghidra.app.script import GhidraScript
from ghidra.util.task import TaskMonitor

from ghidra.framework.preferences import Preferences

from javax.swing import (
    JLabel,
    JTextField,
    JCheckBox,
    JButton,
    JOptionPane,
    JDialog,
    BorderFactory,
    JPasswordField,
)
from java.awt import GridBagLayout, GridBagConstraints, Insets, Dimension, Color
from java.awt import Frame
from java.awt.event import ActionListener

from typing import Tuple, List

PREF_KEY_URL = "sighthouse.form.url"
PREF_KEY_USERNAME = "sighthouse.form.username"
PREF_KEY_PASSWORD = "sighthouse.form.password"
PREF_KEY_VERIFY_HOST = "sighthouse.form.verify_host"
PREF_KEY_FORCE_SUBMISSION = "sighthouse.form.force_submission"


import argparse
import sys
import jpype
from sighthouse.client.SightHouseClient import (
    SightHouseAnalysis,
    LoggingSighthouse,
    Section,
    Function,
)


class LoggingGhidraSighthouse(LoggingSighthouse):

    def __init__(self, ghidrascript: GhidraScript) -> None:
        """Initialize logging class"""
        self._ghidrascript = ghidrascript
        pass

    def error(self, message: str):
        """Show an error message

        Args:
            message (str): The message to show
        """
        Msg.showError(self._ghidrascript, None, getCategory(), str(message))

    def warning(self, message: str):
        """Show an warning message

        Args:
            message (str): The message to show
        """
        Msg.warn(self._ghidrascript, str(message))

    def info(self, message: str):
        """Show an info message

        Args:
            message (str): The message to show
        """
        Msg.info(self._ghidrascript, str(message))
        print(str(message))


class SightHouseGhidraAnalysis(SightHouseAnalysis):

    def __init__(
        self,
        prgm: Program,
        url: str,
        username: str,
        password: str,
        verify_host: bool = True,
        force_submission: bool = False,
        options: dict = None,
    ):
        """Initialize SightHouseGhidraAnalysis

        Args:
            prgm (Program): program to analyze
            url (str): server url
            username (str): username to connect to it
            password (str): password to connect to it
        """
        self.prgm = prgm
        self.ghidrascript = this
        super().__init__(
            username,
            password,
            url,
            LoggingGhidraSighthouse(self.ghidrascript),
            verify_host,
            force_submission,
            options=options,
        )

    def get_current_arch(self) -> None:
        """get current architecture and translate to ghidra one"""
        return self.prgm.getLanguageID().toString()

    def update_progress(self, message: str) -> None:
        """show an update progress

        Args:
            message (str): message to show
        """
        print(message)

    def get_program_name(self) -> str:
        """Get program name

        Returns:
            str: the program name
        """
        return self.prgm.getName()

    def get_current_binary(self) -> bytes:
        """Retrieve the current binaries in bytes

        Returns:
            bytes: the content in bytes of the current binaries
        """
        allFileBytes = self.prgm.getMemory().getAllFileBytes()
        if allFileBytes.isEmpty():
            self._logger.warning(
                "Exporting a program with no file source bytes is not supported"
            )
            return None
        if allFileBytes.size() > 1:
            self._logger.warning(
                "Program contains more than 1 file source, Only bytes from the primary (first) file source will be exported"
            )

        fileBytes = allFileBytes.get(0)
        size = fileBytes.getSize()
        ByteArray = jpype.JArray(jpype.JByte)
        all_bytes = ByteArray([0] * size)
        fileBytes.getOriginalBytes(0, all_bytes)
        return all_bytes

    def get_sections(self) -> List[Section]:
        """Get sections of the binary

        Returns:
            List[Section]: list sections
        """

        memory = self.prgm.getMemory()
        blocks = memory.getBlocks()
        res = []
        for b in blocks:
            perms = "R" if b.isRead() else " "
            perms += "W" if b.isWrite() else " "
            perms += "X" if b.isExecute() else " "
            for b_source in b.getSourceInfos():
                res.append(
                    Section(
                        b.getName(),
                        b_source.getMinAddress().getOffset(),
                        b_source.getMaxAddress().getOffset(),
                        b_source.getFileBytesOffset(),
                        perms,
                        "",
                    )
                )
        #   b.getStart().getOffset(), b.getEnd().getOffset(),  	b.getFileBytesOffset()
        # 	isExecute()
        #   isRead()
        #   isWrite()
        #   isInitialized()
        return res

    def get_hash_program(self) -> str:
        """get hash of program

        Returns:
            str: sha256 string
        """
        return self.prgm.getExecutableSHA256()

    def is_thumb(self, address: "Address") -> bool:
        """Indicate if the code at the given address is Thumb

        Retuns:
            bool: True if the code located at the given address is thumb
        """
        t_reg = self.prgm.getRegister("TMode")
        if not t_reg:
            return False

        context = self.prgm.getProgramContext()
        value = context.getRegisterValue(t_reg, address)
        if not value:
            return False

        return value.getUnsignedValue().longValue() == 1

    def get_functions(self, section: Section) -> List[Function]:
        """get functions

        Args:
            section (Section): section

        Returns:
            List[Function]: list of function inside the section
        """
        ret_funcs = []
        functions = self.prgm.getFunctionManager().getFunctions(True)
        for function in functions:
            func_start = function.getEntryPoint().getOffset()
            # Check if the function's start address is within the block's range
            if section.start <= func_start <= section.end:
                details = {}
                if self.is_thumb(function.getEntryPoint()):
                    details.update({"thumb": True})

                ret_funcs.append(
                    Function(
                        function.getName(), func_start - section.start, details=details
                    )
                )

        return ret_funcs

    def add_tag(self, address: int, tag: str, message: str) -> None:
        """Add a tag on the SRE

        Args:
            address (int): address where put the tag
            tag (str): tag of message
            message (str): message to show
        """
        addrSpace = self.prgm.getAddressFactory().getDefaultAddressSpace()
        addr = addrSpace.getAddress(address)
        setPlateComment(addr, message)
        createBookmark(addr, "SightHouse matches", message)

    def run(self, monitor) -> None:
        """Run the complete analysis"""
        self._monitor = monitor
        self._monitor.initialize(10)
        # Create a transaction to save/rollback changes
        transaction = self.prgm.startTransaction(self.__class__.__name__)
        commit = True
        try:
            super().run()
        except:
            commit = False
        finally:
            self.prgm.endTransaction(transaction, commit)


class UserFormPlugin:
    def __init__(self, program, title="SighthousePlugin Configuration"):
        # Create the JDialog instance
        parent = Frame()
        self.program = program
        self.dialog = JDialog(parent, title, True)  # Modal dialog
        self.dialog.setSize(400, 300)
        self.dialog.setLayout(GridBagLayout())  # Use a flexible layout

        # Initialize layout constraints
        self.gbc = GridBagConstraints()
        self.gbc.insets = Insets(5, 5, 5, 5)  # Padding
        self.gbc.fill = GridBagConstraints.HORIZONTAL

        # Create and add components
        self.url_field = self.create_textfield(30)
        self.username_field = self.create_textfield(20)
        self.password_field = self.create_passwordfield(20)
        self.verify_host_field = self.create_checkbox()
        self.force_submission_field = self.create_checkbox()
        self.bob_ross_field = self.create_checkbox()

        self.load_form_data()

        self.add_components()

        # Center the dialog on the screen
        self.dialog.setLocationRelativeTo(None)

    def add_components(self):
        """Add components to the dialog."""

        # URL Label and Field
        self.gbc.gridx = 0
        self.gbc.gridy = 0
        self.dialog.add(self.create_label("URL:"), self.gbc)

        self.gbc.gridx = 1
        self.dialog.add(self.url_field, self.gbc)

        # Username Label and Field
        self.gbc.gridx = 0
        self.gbc.gridy = 1
        self.dialog.add(self.create_label("Username:"), self.gbc)

        self.gbc.gridx = 1
        self.dialog.add(self.username_field, self.gbc)

        # Password Label and Field
        self.gbc.gridx = 0
        self.gbc.gridy = 2
        self.dialog.add(self.create_label("Password:"), self.gbc)

        # Password Label and Field
        self.gbc.gridx = 1
        self.dialog.add(self.password_field, self.gbc)

        # Label for verify Host
        self.gbc.gridx = 0
        self.gbc.gridy = 3
        self.dialog.add(self.create_label("Verify host:"), self.gbc)

        # Field for verify host
        self.gbc.gridx = 1
        self.dialog.add(self.verify_host_field, self.gbc)

        # Label for force submission
        self.gbc.gridx = 0
        self.gbc.gridy = 4
        self.dialog.add(self.create_label("Force submission:"), self.gbc)

        # Field for force submission
        self.gbc.gridx = 1
        self.dialog.add(self.force_submission_field, self.gbc)

        # Label for Bob Ross
        self.gbc.gridx = 0
        self.gbc.gridy = 5
        self.dialog.add(self.create_label("Bob Ross:"), self.gbc)

        # Field for force submission
        self.gbc.gridx = 1
        self.dialog.add(self.bob_ross_field, self.gbc)

        # Submit Button
        self.gbc.gridx = 0
        self.gbc.gridy = 6
        self.gbc.gridwidth = 2  # Span the button across two columns
        submit_button = JButton("Submit")
        submit_button.setBackground(Color(70, 130, 180))  # Steel Blue
        submit_button.setForeground(Color.WHITE)
        submit_button.setPreferredSize(Dimension(100, 30))

        # Add an ActionListener for the submit button
        submit_button.addActionListener(self.on_submit)

        self.dialog.add(submit_button, self.gbc)

    def create_label(self, text):
        """Create a styled JLabel."""
        label = JLabel(text)
        label.setOpaque(True)
        label.setBackground(Color(240, 240, 240))  # Light gray background
        label.setBorder(BorderFactory.createEmptyBorder(5, 5, 5, 5))
        return label

    def create_textfield(self, columns):
        """Create a styled JTextField."""
        textfield = JTextField(columns)
        textfield.setPreferredSize(Dimension(250, 30))
        textfield.setMinimumSize(Dimension(250, 30))
        textfield.setBorder(
            BorderFactory.createCompoundBorder(
                BorderFactory.createLineBorder(Color(70, 130, 180), 1),  # Outer border
                BorderFactory.createEmptyBorder(2, 2, 2, 2),  # Padding
            )
        )
        return textfield

    def create_checkbox(self):
        """Create a styled JTextField."""
        textfield = JCheckBox()
        textfield.setPreferredSize(Dimension(30, 30))
        textfield.setMinimumSize(Dimension(30, 30))
        textfield.setBorder(
            BorderFactory.createCompoundBorder(
                BorderFactory.createLineBorder(Color(70, 130, 180), 1),  # Outer border
                BorderFactory.createEmptyBorder(2, 2, 2, 2),  # Padding
            )
        )
        return textfield

    def create_passwordfield(self, columns):
        """Create a styled JPasswordField."""
        password_field = JPasswordField(columns)
        password_field.setPreferredSize(Dimension(250, 30))
        password_field.setMinimumSize(Dimension(250, 30))
        password_field.setBorder(
            BorderFactory.createCompoundBorder(
                BorderFactory.createLineBorder(Color(70, 130, 180), 1),  # Outer border
                BorderFactory.createEmptyBorder(2, 2, 2, 2),  # Padding
            )
        )
        return password_field

    def save_form_data(self, url, username, password, verify_host, force_submission):
        """Save form data to Ghidra preferences."""
        # preference_state = Preferences.getPreferenceState()
        Preferences.setProperty(PREF_KEY_URL, url)
        Preferences.setProperty(PREF_KEY_USERNAME, username)
        Preferences.setProperty(PREF_KEY_PASSWORD, password)
        if verify_host:
            Preferences.setProperty(PREF_KEY_VERIFY_HOST, "True")
        else:
            Preferences.setProperty(PREF_KEY_VERIFY_HOST, "False")

        if force_submission:
            Preferences.setProperty(PREF_KEY_FORCE_SUBMISSION, "True")
        else:
            Preferences.setProperty(PREF_KEY_FORCE_SUBMISSION, "False")
        # Preferences.savePreferences()

    def load_form_data(self):
        """Load form data from Ghidra preferences."""
        # preference_state = Preferences.getPreferenceState()
        self.url_field.setText(Preferences.getProperty(PREF_KEY_URL, ""))
        self.username_field.setText(Preferences.getProperty(PREF_KEY_USERNAME, ""))
        self.password_field.setText(Preferences.getProperty(PREF_KEY_PASSWORD, ""))
        if Preferences.getProperty(PREF_KEY_VERIFY_HOST, "True") == "True":
            self.verify_host_field.setSelected(True)
        else:
            self.verify_host_field.setSelected(False)

        if Preferences.getProperty(PREF_KEY_FORCE_SUBMISSION, "True") == "True":
            self.force_submission_field.setSelected(True)
        else:
            self.force_submission_field.setSelected(False)

    def on_submit(self, event):
        """Handle form submission."""
        url = self.url_field.getText()
        username = self.username_field.getText()
        password = "".join(
            self.password_field.getPassword()
        )  # Convert char array to string
        verify_host = self.verify_host_field.isSelected()
        force_submission = self.force_submission_field.isSelected()
        bob_ross = self.bob_ross_field.isSelected()

        # Validate and display user inputs
        if not url or not username or not password:
            JOptionPane.showMessageDialog(
                self.dialog,
                "All fields are required!",
                "Error",
                JOptionPane.ERROR_MESSAGE,
            )
        else:
            self.save_form_data(url, username, password, verify_host, force_submission)
            # JOptionPane.showMessageDialog(
            #    self.dialog,
            #    f"You entered:\nURL: {url}\nUsername: {username}\nPassword: {'*' * len(password)}",
            # )

            # Close the dialog
            self.dialog.dispose()
        analyzer = SightHouseGhidraAnalysis(
            self.program,
            url,
            username,
            password,
            verify_host,
            force_submission,
            options={
                "BobRoss": bob_ross,
            },
        )
        analyzer.run(TaskMonitor.DUMMY)

    def show(self):
        """Display the dialog."""
        self.dialog.setVisible(True)


if __name__ == "__main__":
    ghidrascript = this
    log = LoggingGhidraSighthouse(ghidrascript)
    if currentProgram == None:
        log.error("No program opened!")
        sys.exit(1)
    args = getScriptArgs()
    if len(args) == 0:
        UserFormPlugin(program=currentProgram).show()

        # url = askString("Please enter sighthouse URL", "URL: ", "http://localhost:6669")
        # username = askString("Please enter your username", "Username: ")
        # password = str(askPassword("Password", None).getPasswordChars())
    else:
        parser = argparse.ArgumentParser("SightHouse")
        parser.add_argument("url", help="SightHouse server URL")
        parser.add_argument("username", help="SightHouse server password")
        parser.add_argument("password", help="SightHouse server username")
        parser.add_argument("--debug", action="store_true", help="Activate debug mode")

        args = parser.parse_args(args)
        url = args.url
        username = args.username
        password = args.password

        print(url, username, password)
        analyzer = SightHouseGhidraAnalysis(currentProgram, url, username, password)
        analyzer.run(TaskMonitor.DUMMY)
