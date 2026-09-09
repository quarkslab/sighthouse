//Autodetect script: run Ghidra's native importer to find language/sections.
//@author SightHouse
//@category SightHouse
//@keybinding
//@menupath
//@toolbar

import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.Writer;
import java.io.StringWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.lang.reflect.Modifier;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Program;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.mem.MemoryBlockSourceInfo;
import ghidra.program.database.mem.FileBytes;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

// Minimal config: just the three paths (input binary + output + error log).
class AutodetectConfiguration {
  private String file;
  private String output;
  private String error;

  // Getters 
  public String getFile() { return file; }
  public String getOutput() { return output; }
  public String getErrorLog() { return error; }
}

// One memory block, in the shape the sections REST API / custom loader expect.
// Field names are serialized verbatim by Gson (note snake_case `file_offset`).
class AutodetectSection {
  private String name;
  private long file_offset;
  private long start;
  private long end;
  private String perms;
  private String kind;

  public AutodetectSection(String name, long file_offset, long start, long end, String perms, String kind) {
    this.name = name;
    this.file_offset = file_offset;
    this.start = start;
    this.end = end;
    this.perms = perms;
    this.kind = kind;
  }
}

// Output document: {"language": <id>, "sections": [...]}.
class AutodetectResult {
  private String language;
  private List<AutodetectSection> sections;

  public AutodetectResult(String language, List<AutodetectSection> sections) {
    this.language = language;
    this.sections = sections;
  }
}

public class SightHouseAutodetectScript extends GhidraScript {

  // File offset the block's bytes come from, or -1 for uninitialized (BSS) blocks
  // (the custom loader treats file_offset < 0 as uninitialized).
  private long fileOffsetOf(MemoryBlock block) {
    if (!block.isInitialized()) {
      return -1;
    }
    for (MemoryBlockSourceInfo info : block.getSourceInfos()) {
      long fileBytesOffset = info.getFileBytesOffset();
      if (fileBytesOffset < 0) {
        continue;
      }
      Optional<FileBytes> fileBytes = info.getFileBytes();
      long base = fileBytes.isPresent() ? fileBytes.get().getFileOffset() : 0;
      return base + fileBytesOffset;
    }
    return -1;
  }

  private AutodetectResult detect(Program program) {
    List<AutodetectSection> sections = new ArrayList<AutodetectSection>();
    for (MemoryBlock block : program.getMemory().getBlocks()) {
      String perms = ""
        + (block.isRead() ? 'R' : '-')
        + (block.isWrite() ? 'W' : '-')
        + (block.isExecute() ? 'X' : '-');
      long start = block.getStart().getOffset();
      long end = block.getEnd().getOffset() + 1;
      sections.add(new AutodetectSection(block.getName(), fileOffsetOf(block), start, end, perms, ""));
    }
    return new AutodetectResult(program.getLanguageID().getIdAsString(), sections);
  }

  public void run() throws Exception {
    AutodetectConfiguration config = null;
    String configPath = askString("Enter the path to the autodetect configuration file", "Ok");
    try {
      Gson gson = new GsonBuilder().excludeFieldsWithModifiers(Modifier.TRANSIENT).create();
      config = gson.fromJson(new FileReader(configPath), AutodetectConfiguration.class);

      // Native (Naive?) best-guess import (ELF/PE/Mach-O/...).
      Program program = importFile(new File(config.getFile()));
      if (program == null) {
        throw new Exception("Ghidra could not identify the file format (no loader matched).");
      }

      AutodetectResult result = detect(program);
      Writer writer = new FileWriter(config.getOutput());
      gson.toJson(result, writer);
      writer.flush(); // @important: flush data to file
      writer.close();
    } catch (Exception e) {
      // Dump the stack to stdout + the error log.
      StringWriter sw = new StringWriter();
      PrintWriter pw = new PrintWriter(sw);
      e.printStackTrace(pw);
      println(sw.toString());
      e.printStackTrace();
      if (config != null && config.getErrorLog() != null) {
        Writer writer = new FileWriter(config.getErrorLog());
        writer.write("Autodetect failed:\n" + sw.toString());
        writer.flush(); // @important: flush data to file
        writer.close();
      }
      System.exit(1);
    }
  }
}

