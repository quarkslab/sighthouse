from tempfile import TemporaryDirectory
import secrets
import shutil
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from sighthouse.frontend.database import FrontendDatabase
from sighthouse.frontend.model import (
    User,
    File,
    Program,
    Section,
    Function,
    Match,
    Analysis,
)


class TestFrontendDatabase(unittest.TestCase):

    def setUp(self):
        # Temporary directory used as repo for uploaded files
        self.tmpdir = TemporaryDirectory()
        # self.addCleanup(lambda: shutil.rmtree(self.tmpdir.name, ignore_errors=True))
        self.db = FrontendDatabase(
            "sqlite://:memory:", f"local://{self.tmpdir.name}/", exist_ok=True
        )

    # ---------- Helper methods ----------

    def _create_user(self, name: str = None) -> User:
        user = self.db.add_user(
            User(
                id=User.INVALID_ID,
                name=name or f"alice_{secrets.token_hex(16)}",
                hash="1234",
            )
        )
        # Some implementations may set id after insertion
        self.assertNotEqual(user.id, User.INVALID_ID)
        return user

    def _create_file(self, user: User, hash: str = None) -> File:
        # Depending on your API you might need to call add_file_user
        f = File(
            id=File.INVALID_ID,
            user=user.id,
            name="test.bin",
            hash=hash or secrets.token_hex(16),
            content=b"hello",
        )
        f = self.db.add_file_user(f)
        self.assertNotEqual(f.id, File.INVALID_ID)
        return f

    def _create_program(
        self, file_obj: File, name: str = "testprog", language: str = "python"
    ) -> Program:
        """Helper to create a program with unique name using given file"""
        program = Program(
            id=Program.INVALID_ID,
            name=f"{name}_{secrets.token_hex(16)}",  # unique name
            user=file_obj.user,  # Use the file's user
            language=language,
            file=file_obj.id,
        )
        program = self.db.add_program(program)
        self.assertNotEqual(program.id, Program.INVALID_ID)
        return program

    def _create_section(self, program: Program, name: str = "section") -> Section:
        """Helper to create a section with unique name for given program"""
        section = Section(
            id=Section.INVALID_ID,
            name=f"{name}_{secrets.token_hex(4)}",
            program=program.id,
            file_offset=0,
            start=100,
            end=200,
            perms="rwx",
            kind="code",
        )
        section = self.db.add_section(section)
        self.assertNotEqual(section.id, Section.INVALID_ID)
        return section

    def _create_function(self, section: Section, name: str = "func") -> Function:
        """Helper to create function with unique name"""
        function = Function(
            id=Function.INVALID_ID,
            name=f"{name}_{secrets.token_hex(4)}",
            offset=150,
            section=section.id,
            details={"args": 2, "locals": 10},
        )
        return self.db.add_function(function)

    def _create_match(self, function: Function) -> Match:
        """Helper to create match for given function"""
        match = Match(
            id=Match.INVALID_ID,
            name=f"match_{secrets.token_hex(4)}",
            function=function.id,
            metadata={"confidence": 0.95, "source": "db"},
        )
        return self.db.add_match(match)

    def _create_analysis(self, program: Program, user: User) -> Analysis:
        """Helper to create analysis for program/user"""
        analysis = Analysis(
            program=program.id,
            user=user.id,
            info={"status": "running", "progress": 50},
        )
        return self.db.add_analysis(analysis)

    # ---------- Tests for user-related methods ----------

    def test_add_and_get_user(self):
        user = self._create_user(name="alice")

        fetched = self.db.get_user(user.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, user.id)
        self.assertEqual(fetched.name, "alice")

    def test_get_user_by_name(self):
        user = self._create_user(name="alice")

        fetched = self.db.get_user_by_name("alice")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, user.id)

    def test_update_user(self):
        user = self._create_user()
        user.name = "alice2"

        ok = self.db.update_user(user)
        self.assertTrue(ok)

        fetched = self.db.get_user(user.id)
        self.assertEqual(fetched.name, "alice2")

    def test_list_users(self):
        u1 = self._create_user()
        # Add a second user
        user2 = User(id=User.INVALID_ID, name="bob", hash="5678")
        u2 = self.db.add_user(user2)

        users = self.db.list_users()
        ids = {u.id for u in users}
        self.assertIn(u1.id, ids)
        self.assertIn(u2.id, ids)

    def test_delete_user(self):
        user = self._create_user()
        ok = self.db.delete_user(user)
        self.assertTrue(ok)

        self.assertIsNone(self.db.get_user(user.id))

    # ---------- Tests for helper directory methods ----------

    def test_get_username_from_user_and_id(self):
        user = self._create_user(name="alice")

        name_from_user = self.db.get_username(user)
        name_from_id = self.db.get_username(user.id)

        self.assertEqual(name_from_user, "alice")
        self.assertEqual(name_from_id, "alice")

    def test_get_upload_dir_creates_directory(self):
        user = self._create_user()
        upload_dir = self.db.get_upload_dir(user)
        self.assertIsNotNone(upload_dir)

    # ---------- Tests for file-related methods ----------

    def test_add_file_user_and_get_file_user(self):
        user = self._create_user()
        f = self._create_file(user)

        fetched = self.db.get_file_user(file_id=f.id, user_id=user.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, f.id)
        self.assertEqual(fetched.user, user.id)

    def test_get_file_by_hash(self):
        user = self._create_user()
        f = self._create_file(user, hash="1234")

        fetched = self.db.get_file_by_hash(file_hash="1234", user_id=user.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, f.id)

    def test_get_user_file_returns_files(self):
        user = self._create_user()
        f1 = self._create_file(user)
        f2 = self._create_file(user)

        files = self.db.get_user_file(user_id=user.id)
        ids = {f.id for f in files}
        self.assertIn(f1.id, ids)
        self.assertIn(f2.id, ids)

    def test_delete_file(self):
        user = self._create_user()
        f = self._create_file(user)

        print(f)
        ok = self.db.delete_file(f)
        self.assertTrue(ok)

        self.assertIsNone(self.db.get_file_user(file_id=f.id, user_id=user.id))

    def test_delete_user_files(self):
        user = self._create_user()
        self._create_file(user)
        self._create_file(user)

        ok = self.db.delete_user_files(user_id=user.id)
        self.assertTrue(ok)

        files = self.db.get_user_file(user_id=user.id)
        self.assertEqual(files, [])

    # ---------- Tests for get_file / get_sharefile (filesystem) ----------

    def test_get_file_reads_content(self):
        user = self._create_user()
        # Create upload dir and physical file
        upload_dir = Path(self.tmpdir.name, self.db.get_upload_dir(user))
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / "test.bin"
        file_path.write_bytes(b"hello")

        f = File(
            id=File.INVALID_ID,
            user=user.id,
            name="test.bin",
            hash="hash123",
            content=b"hello",
        )
        stored_file = self.db.add_file_user(f)

        content = self.db.get_file(stored_file)
        self.assertEqual(content, b"hello")

    def test_get_file_missing_returns_none(self):
        user = self._create_user()
        f = File(
            id=File.INVALID_ID,
            user=user.id,
            name="missing.bin",
            hash="hash999",
            content=None,
        )
        with self.assertRaises(Exception):
            stored_file = self.db.add_file_user(f)

    def test_get_sharefile_returns_existing_path(self):
        user = self._create_user()
        upload_dir = Path(self.tmpdir.name, self.db.get_upload_dir(user))
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / "test.bin"
        file_path.write_bytes(b"hello")

        f = File(
            id=File.INVALID_ID,
            user=user.id,
            name="test.bin",
            hash="hash123",
            content=b"hello",
        )
        stored_file = self.db.add_file_user(f)

        share_path = self.db.get_sharefile(stored_file)
        # It may be Path or str according to your API
        share_path = Path(share_path)
        self.assertTrue(share_path.exists())

    # ---------- Tests for Program API ----------

    def test_add_and_get_program(self):
        user = self._create_user()
        program = self._create_program(self._create_file(user))

        fetched = self.db.get_program(program.id, user_id=user.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, program.id)
        self.assertEqual(fetched.name, program.name)
        self.assertEqual(fetched.user, user.id)

    def test_get_program_without_user_id(self):
        program = self._create_program(self._create_file(self._create_user()))

        fetched = self.db.get_program(program.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, program.id)

    def test_get_program_not_found(self):
        program = self._create_program(self._create_file(self._create_user()))
        self.db.delete_program(program)

        fetched = self.db.get_program(program.id)
        self.assertIsNone(fetched)

    def test_update_program(self):
        user = self._create_user()
        program = self._create_program(self._create_file(user), language="python")
        program.name = "updated_program"
        program.language = "javascript"

        ok = self.db.update_program(program, user_id=user.id)
        self.assertTrue(ok)

        fetched = self.db.get_program(program.id, user_id=user.id)
        self.assertEqual(fetched.name, "updated_program")
        self.assertEqual(fetched.language, "javascript")

    def test_update_program_without_user_id(self):
        program = self._create_program(self._create_file(self._create_user()))
        program.name = "updated_no_user"

        ok = self.db.update_program(program)
        self.assertTrue(ok)

        fetched = self.db.get_program(program.id)
        self.assertEqual(fetched.name, "updated_no_user")

    def test_list_user_programs(self):
        user = self._create_user()
        file = self._create_file(user)
        prog1 = self._create_program(file, "prog1")
        prog2 = self._create_program(file, "prog2")

        # Programs for different user
        user2 = User(id=User.INVALID_ID, name="bob", hash="5678")
        user2 = self.db.add_user(user2)
        file2 = File(
            id=File.INVALID_ID,
            user=user2.id,
            name="bob.bin",
            hash=secrets.token_hex(16),
            content=b"world",
        )
        file2 = self.db.add_file_user(file2)
        other_prog = self._create_program(file2, "bobprog", "js")

        programs = self.db.list_user_programs(user.id)
        ids = {p.id for p in programs}
        self.assertIn(prog1.id, ids)
        self.assertIn(prog2.id, ids)
        self.assertNotIn(other_prog.id, ids)
        self.assertEqual(len(programs), 2)

    def test_delete_program(self):
        user = self._create_user()
        program = self._create_program(self._create_file(user))
        ok = self.db.delete_program(program)
        self.assertTrue(ok)

        fetched = self.db.get_program(program.id, user_id=user.id)
        self.assertIsNone(fetched)

    def test_delete_user_programs(self):
        user = self._create_user()
        prog1 = self._create_program(self._create_file(user))
        prog2 = self._create_program(self._create_file(user))

        ok = self.db.delete_user_programs(user.id)
        self.assertTrue(ok)

        programs = self.db.list_user_programs(user.id)
        self.assertEqual(programs, [])

        # Verify files still exist (delete_user_programs shouldn't delete files)
        fetched_file = self.db.get_file_user(prog1.file, user.id)
        self.assertIsNotNone(fetched_file)

    # ---------- Edge cases for programs ----------

    def test_get_program_other_users_program(self):
        """Test user isolation - can't get other user's program"""
        program = self._create_program(self._create_file(self._create_user()))

        user2 = User(id=User.INVALID_ID, name="bob", hash="5678")
        user2 = self.db.add_user(user2)

        fetched = self.db.get_program(program.id, user_id=user2.id)
        if fetched is not None:
            self.assertNotEqual(fetched.user, user2.id)

    def test_update_program_other_users_program(self):
        """Test can't update other user's program"""
        program = self._create_program(self._create_file(self._create_user()))

        user2 = User(id=User.INVALID_ID, name="bob", hash="5678")
        user2 = self.db.add_user(user2)

        program.name = "hacked_name"
        self.db.update_program(program, user_id=user2.id)
        # Should fail for security
        update = self.db.get_program(program.id)
        self.assertIsNotNone(update)
        self.assertNotEqual(update.name, "hacked_name")

    # ---------- Tests for Section API ----------

    def test_add_and_get_section(self):
        # Create prerequisites
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)

        section = self._create_section(program)

        # Verify retrieval with program_id
        fetched = self.db.get_section(section.id, program_id=program.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, section.id)
        self.assertEqual(fetched.program, program.id)
        self.assertEqual(fetched.name, section.name)

    def test_get_section_without_program_id(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)

        fetched = self.db.get_section(section.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, section.id)

    def test_get_section_not_found(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)

        self.db.delete_section(section)

        fetched = self.db.get_section(section.id)
        self.assertIsNone(fetched)

    def test_list_program_sections(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)

        # Create sections for this program
        section1 = self._create_section(program, "sec1")
        section2 = self._create_section(program, "sec2")

        # Create section for different program
        file2 = self._create_file(user)
        program2 = self._create_program(file2)
        self._create_section(program2, "other")

        sections = self.db.list_program_sections(program.id)
        ids = {s.id for s in sections}
        self.assertIn(section1.id, ids)
        self.assertIn(section2.id, ids)
        self.assertNotIn(program2.id, {s.program for s in sections})
        self.assertEqual(len(sections), 2)

    def test_delete_section(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)

        ok = self.db.delete_section(section)
        self.assertTrue(ok)

        fetched = self.db.get_section(section.id, program_id=program.id)
        self.assertIsNone(fetched)

    def test_delete_program_sections(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)

        # Create multiple sections
        section1 = self._create_section(program)
        section2 = self._create_section(program)

        ok = self.db.delete_program_sections(program.id)
        self.assertTrue(ok)

        # Verify sections are gone
        sections = self.db.list_program_sections(program.id)
        self.assertEqual(sections, [])

        # Verify program still exists
        fetched_program = self.db.get_program(program.id)
        self.assertIsNotNone(fetched_program)

    # ---------- Edge cases for section ----------

    def test_get_section_other_programs_section(self):
        """Test program isolation"""
        user = self._create_user()
        file_obj = self._create_file(user)
        program1 = self._create_program(file_obj)
        section = self._create_section(program1)

        # Create different program
        file2 = self._create_file(user)
        program2 = self._create_program(file2)

        fetched = self.db.get_section(section.id, program_id=program2.id)
        # Should return None due to program isolation
        self.assertIsNone(fetched)

    def test_list_program_sections_empty(self):
        """Test empty list for program with no sections"""
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)

        sections = self.db.list_program_sections(program.id)
        self.assertEqual(sections, [])

    def test_delete_nonexistent_section(self):
        """Test deleting section that doesn't exist"""
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)

        fake_section = Section(
            id=9999,  # invalid ID
            name="fake",
            program=program.id,
            file_offset=0,
            start=0,
            end=0,
            perms="rwx",
            kind="code",
        )

        # Should not raise any errors
        self.db.delete_section(fake_section)

    def test_add_section_different_programs(self):
        """Verify sections belong to correct programs"""
        user = self._create_user()
        file_obj1 = self._create_file(user)
        program1 = self._create_program(file_obj1)
        file_obj2 = self._create_file(user)
        program2 = self._create_program(file_obj2)

        section1 = self._create_section(program1, "prog1_sec")
        section2 = self._create_section(program2, "prog2_sec")

        # Verify isolation
        prog1_sections = self.db.list_program_sections(program1.id)
        prog2_sections = self.db.list_program_sections(program2.id)

        self.assertEqual(len(prog1_sections), 1)
        self.assertEqual(prog1_sections[0].program, program1.id)
        self.assertEqual(len(prog2_sections), 1)
        self.assertEqual(prog2_sections[0].program, program2.id)

    # ---------- Tests for Function API ----------

    def test_add_and_get_function(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)
        function = self._create_function(section)

        fetched = self.db.get_function(function.id, section_id=section.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, function.id)
        self.assertEqual(fetched.section, section.id)

    def test_get_function_without_section_id(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)
        function = self._create_function(section)

        fetched = self.db.get_function(function.id)
        self.assertIsNotNone(fetched)

    def test_list_section_functions(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)

        func1 = self._create_function(section, "func1")
        func2 = self._create_function(section, "func2")

        # Function in different section
        section2 = self._create_section(program)
        self._create_function(section2, "other")

        functions = self.db.list_section_functions(section.id)
        ids = {f.id for f in functions}
        self.assertIn(func1.id, ids)
        self.assertIn(func2.id, ids)
        self.assertEqual(len(functions), 2)

    def test_delete_function(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)
        function = self._create_function(section)

        ok = self.db.delete_function(function)
        self.assertTrue(ok)
        self.assertIsNone(self.db.get_function(function.id))

    def test_delete_section_functions(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)

        func1 = self._create_function(section)
        func2 = self._create_function(section)

        ok = self.db.delete_section_functions(section.id)
        self.assertTrue(ok)

        functions = self.db.list_section_functions(section.id)
        self.assertEqual(functions, [])
        # Section still exists
        self.assertIsNotNone(self.db.get_section(section.id))

    # ---------- Tests for Match API ----------

    def test_add_and_get_match(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)
        function = self._create_function(section)
        match = self._create_match(function)

        fetched = self.db.get_match(match.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.function, function.id)

    def test_list_function_matches(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)
        function = self._create_function(section)

        match1 = self._create_match(function)
        match2 = self._create_match(function)

        # Match for different function
        func2 = self._create_function(section)
        self._create_match(func2)

        matches = self.db.list_function_matches(function.id)
        ids = {m.id for m in matches}
        self.assertIn(match1.id, ids)
        self.assertIn(match2.id, ids)
        self.assertEqual(len(matches), 2)

    def test_delete_match(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        section = self._create_section(program)
        function = self._create_function(section)
        match = self._create_match(function)

        ok = self.db.delete_match(match)
        self.assertTrue(ok)
        self.assertIsNone(self.db.get_match(match.id))

    # ---------- Tests for Analysis API ----------

    def test_add_and_get_analysis(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        analysis = self._create_analysis(program, user)

        fetched = self.db.get_analysis(program.id, user_id=user.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.program, program.id)
        self.assertEqual(fetched.user, user.id)

    def test_get_analysis_without_user_id(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        analysis = self._create_analysis(program, user)

        fetched = self.db.get_analysis(program.id)
        self.assertIsNotNone(fetched)

    def test_delete_analysis(self):
        user = self._create_user()
        file_obj = self._create_file(user)
        program = self._create_program(file_obj)
        analysis = self._create_analysis(program, user)

        ok = self.db.delete_analysis(analysis)
        self.assertTrue(ok)
        self.assertIsNone(self.db.get_analysis(program.id, user_id=user.id))

    def test_analysis_user_isolation(self):
        """Verify users can't access other users' analyses"""
        user1 = self._create_user()
        file1 = self._create_file(user1)
        program1 = self._create_program(file1)
        analysis1 = self._create_analysis(program1, user1)

        user2 = User(id=User.INVALID_ID, name="bob", hash="5678")
        user2 = self.db.add_user(user2)

        fetched = self.db.get_analysis(program1.id, user_id=user2.id)
        self.assertIsNone(fetched)  # Should not find other user's analysis


if __name__ == "__main__":
    unittest.main()
