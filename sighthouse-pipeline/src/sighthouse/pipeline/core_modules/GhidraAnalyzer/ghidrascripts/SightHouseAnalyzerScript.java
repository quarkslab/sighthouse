// Script that extract BSIM signatures and send them to backend
//@author Fenrisfulsur, MadSquirrels 
//@category Sighthouse
//@keybinding 
//@menupath 
//@toolbar 

// Java imports
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Types;

import java.io.FileReader;
import java.io.FileInputStream;
import java.io.IOException;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Iterator;

// Ghidra imports
import ghidra.app.script.GhidraScript;
import ghidra.app.util.importer.MessageLog;
import ghidra.app.plugin.core.disassembler.EntryPointAnalyzer;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Program;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.mem.MemoryAccessException;
import ghidra.program.model.symbol.SourceType;
import ghidra.util.exception.CancelledException;
import ghidra.util.exception.DuplicateFileException;
import ghidra.util.Msg;

// BSIM signature generation
import generic.lsh.vector.LSHVector;
import generic.lsh.vector.LSHVectorFactory;
import generic.lsh.vector.WeightedLSHCosineVectorFactory;
import generic.lsh.vector.WeightFactory;
import generic.lsh.vector.IDFLookup;
import ghidra.features.bsim.query.GenSignatures;
import ghidra.features.bsim.query.client.tables.WeightTable;
import ghidra.features.bsim.query.client.tables.IdfLookupTable;
import ghidra.features.bsim.query.client.tables.KeyValueTable;
import ghidra.features.bsim.query.description.DescriptionManager;
import ghidra.features.bsim.query.description.FunctionDescription;
import ghidra.features.bsim.query.description.SignatureRecord;

// FIDB signature generation
import ghidra.feature.fid.service.FidService;
import ghidra.feature.fid.hash.FidHasher;
import ghidra.feature.fid.hash.FidHashQuad;

// Name demangling
import ghidra.app.cmd.label.DemanglerCmd;
import ghidra.app.util.demangler.DemanglerOptions;

// JSON imports
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.lang.reflect.Modifier;

// --- Configuration Stuff -----------------------------------------------------

class SightHouseConfiguration {
  private String directory;
  private String metadata;
  private List<DatabaseConfiguration> databases;
  private BsimConfiguration bsim;
  private FidbConfiguration fidb;

  // Getters and Setters
  public String getDirectory() { return directory; }
  public List<DatabaseConfiguration> getDatabases() { return databases; }
  public BsimConfiguration getBsim() { return bsim; }
  public FidbConfiguration getFidb() { return fidb; }
  public String getRawMetadata() { return metadata; }
}

class BsimConfiguration {
  private int min_instructions = 10;    // Mininum number of instruction to filter function
  private int max_instructions = -1;    // Maximum number of instruction to filter function (No maximum by default)

  // Getters and Setters
  public int getMinNumberOfInstructions() { return min_instructions; }
  public int getMaxNumberOfInstructions() { return max_instructions; }
}

class FidbConfiguration {
  private int min_instructions = 2;     // Mininum number of instruction to filter function
  private int max_instructions = -1;    // Maximum number of instruction to filter function (No maximum by default)

  // Getters and Setters
  public int getMinNumberOfInstructions() { return min_instructions; }
  public int getMaxNumberOfInstructions() { return max_instructions; }
}

class DatabaseConfiguration {
  private String url;
  private String username;
  private String password;

  // Getters and Setters
  public String getUrl() { return url; }
  public String getUsername() { return username; }
  public String getPassword() { return password; }
}

// --- SightHouse Database DAO -------------------------------------------------

// JDBC controller for the SightHouse custom tables.
class SightHouseDatabase {

  private Connection connection;

  public SightHouseDatabase(String url, String username, String password) throws SQLException {
    this.connection = DriverManager.getConnection(toJdbcUrl(url), username, password);
    this.connection.setAutoCommit(false);
  }

  // Turn a configuration url ("postgresql://user@host:5432/db") into a JDBC url.
  private static String toJdbcUrl(String url) throws SQLException {
    if (!url.startsWith("postgresql://") && !url.startsWith("postgres://")) {
      throw new SQLException("Unsupported database url (expected postgresql://): " + url);
    }
    int schemeEnd = url.indexOf("://") + 3;
    int at = url.indexOf('@', schemeEnd);
    String authority = (at >= 0) ? url.substring(at + 1) : url.substring(schemeEnd);
    return "jdbc:postgresql://" + authority;
  }

  // Load the lshvector weights into the extension for this connection.
  // Important: Must run before any operation on vectors
  public void loadVectorWeights() throws SQLException {
    try (Statement st = this.connection.createStatement();
         ResultSet rs = st.executeQuery("SELECT lsh_load()")) {
      while (rs.next()) {
        // drain
      }
    }
  }

  // Build the LSH vector factory from the DB weight tables.
  public LSHVectorFactory buildVectorFactory() throws SQLException {
    WeightTable weightTable = new WeightTable();
    IdfLookupTable idfLookupTable = new IdfLookupTable();
    KeyValueTable keyValueTable = new KeyValueTable();
    weightTable.setConnection(this.connection);
    idfLookupTable.setConnection(this.connection);
    keyValueTable.setConnection(this.connection);

    WeightFactory weightFactory = new WeightFactory();
    IDFLookup idfLookup = new IDFLookup();
    weightTable.recoverWeights(weightFactory);
    idfLookupTable.recoverIDFLookup(idfLookup);
    int settings = Integer.parseInt(keyValueTable.getValue("settings"));

    LSHVectorFactory factory = new WeightedLSHCosineVectorFactory();
    factory.set(weightFactory, idfLookup, settings);
    return factory;
  }

  private int getOrInsertString(String table, String value) throws SQLException {
    // Insert first, ignoring the row if another worker inserted it concurrently.
    String insert = "INSERT INTO " + table + " (val) VALUES (?) ON CONFLICT (val) DO NOTHING RETURNING id";
    try (PreparedStatement pstmt = this.connection.prepareStatement(insert)) {
      pstmt.setString(1, value);
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getInt("id");
        }
      }
    }
    // Already present: fetch its id.
    // @NOTE: We have to select the whole DB because of the ON CONFLICT DO NOTHING clause in 
    //        the above statement. Other options would be to use ON CONFLICT DO UPDATE but 
    //        it can create "holes" in the identifiers.
    String select = "SELECT id FROM " + table + " WHERE val = ?";
    try (PreparedStatement pstmt = this.connection.prepareStatement(select)) {
      pstmt.setString(1, value);
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getInt("id");
        }
      }
    }
    throw new SQLException("Failed to insert or fetch value in " + table + ": " + value);
  }

  public long getOrInsertProject(String origin, String name, String version) throws SQLException {
    if (origin == null || name == null || version == null) {
      throw new IllegalArgumentException("project origin/name/version must not be null");
    }
    Long id = this.selectProjectId(origin, name, version);
    if (id != null) {
      return id;
    }
    // Not found: insert, ignoring the row if another worker inserted it concurrently.
    String insert = "INSERT INTO project (origin, name, version) VALUES (?, ?, ?) " +
      "ON CONFLICT (origin, name, version) DO NOTHING RETURNING id";
    try (PreparedStatement pstmt = this.connection.prepareStatement(insert)) {
      pstmt.setString(1, origin);
      pstmt.setString(2, name);
      pstmt.setString(3, version);
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getLong("id");
        }
      }
    }
    // A concurrent insert won the race: fetch its id.
    // @NOTE: We have to select the whole DB because of the ON CONFLICT DO NOTHING clause in 
    //        the above statement. Other options would be to use ON CONFLICT DO UPDATE but 
    //        it can create "holes" in the identifiers.
    id = this.selectProjectId(origin, name, version);
    if (id != null) {
      return id;
    }
    throw new SQLException("Failed to insert or fetch project");
  }

  private Long selectProjectId(String origin, String name, String version) throws SQLException {
    String select = "SELECT id FROM project WHERE origin = ? AND name = ? AND version = ?";
    try (PreparedStatement pstmt = this.connection.prepareStatement(select)) {
      pstmt.setString(1, origin);
      pstmt.setString(2, name);
      pstmt.setString(3, version);
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getLong("id");
        }
      }
    }
    return null;
  }

  public Long getProgramIdByMd5(String md5) throws SQLException {
    String sql = "SELECT id FROM program WHERE md5 = ?";
    try (PreparedStatement pstmt = this.connection.prepareStatement(sql)) {
      pstmt.setString(1, md5);
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getLong("id");
        }
      }
    }
    return null;
  }

  public long insertProgram(String md5, String name, int idArch) throws SQLException {
    String sql = "INSERT INTO program (md5, name, id_arch) VALUES (?, ?, ?) RETURNING id";
    try (PreparedStatement pstmt = this.connection.prepareStatement(sql)) {
      pstmt.setString(1, md5);
      pstmt.setString(2, name);
      pstmt.setInt(3, idArch);
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getLong("id");
        }
      }
    }
    throw new SQLException("Failed to insert program");
  }

  public void linkProjectProgram(long idProject, long idProgram) throws SQLException {
    String sql = "INSERT INTO project_program (id_project, id_program) VALUES (?, ?) ON CONFLICT DO NOTHING";
    try (PreparedStatement pstmt = this.connection.prepareStatement(sql)) {
      pstmt.setLong(1, idProject);
      pstmt.setLong(2, idProgram);
      pstmt.executeUpdate();
    }
  }

  public long getOrInsertFidb(long fullHash, long specificHash,
      int specificHashAdditionalSize, int codeUnitSize) throws SQLException {
    String insert = "INSERT INTO fidb " +
      "(full_hash, specific_hash, specific_hash_additional_size, code_unit_size) VALUES (?, ?, ?, ?) " +
      "ON CONFLICT (full_hash, specific_hash, specific_hash_additional_size, code_unit_size) DO NOTHING RETURNING id";
    try (PreparedStatement pstmt = this.connection.prepareStatement(insert)) {
      pstmt.setLong(1, fullHash);
      pstmt.setLong(2, specificHash);
      pstmt.setInt(3, specificHashAdditionalSize);
      pstmt.setInt(4, codeUnitSize);
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getLong("id");
        }
      }
    }
    // Already present: fetch its id.
    // @NOTE: We have to select the whole DB because of the ON CONFLICT DO NOTHING clause in 
    //        the above statement. Other options would be to use ON CONFLICT DO UPDATE but 
    //        it can create "holes" in the identifiers.
    String select = "SELECT id FROM fidb WHERE full_hash = ? AND specific_hash = ? " +
      "AND specific_hash_additional_size = ? AND code_unit_size = ?";
    try (PreparedStatement pstmt = this.connection.prepareStatement(select)) {
      pstmt.setLong(1, fullHash);
      pstmt.setLong(2, specificHash);
      pstmt.setInt(3, specificHashAdditionalSize);
      pstmt.setInt(4, codeUnitSize);
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getLong("id");
        }
      }
    }
    throw new SQLException("Failed to insert or fetch FID hash record");
  }

  public long insertVector(String vectorSql) throws SQLException {
    String sql = "SELECT insert_vec(?::lshvector)";
    try (PreparedStatement pstmt = this.connection.prepareStatement(sql)) {
      pstmt.setString(1, vectorSql);
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getLong(1);
        }
      }
    }
    throw new SQLException("insert_vec returned no id");
  }

  // Insert a function carrying at least one signature (id_vector and/or id_fidb may be null).
  public long insertFunction(long idProgram, String name, Long idVector, Long idFidb) throws SQLException {
    String sql = "INSERT INTO functions (id_program, name, id_vector, id_fidb) VALUES (?, ?, ?, ?) RETURNING id";
    try (PreparedStatement pstmt = this.connection.prepareStatement(sql)) {
      pstmt.setLong(1, idProgram);
      pstmt.setString(2, name);
      if (idVector != null) {
        pstmt.setLong(3, idVector);
      } else {
        pstmt.setNull(3, Types.BIGINT);
      }
      if (idFidb != null) {
        pstmt.setLong(4, idFidb);
      } else {
        pstmt.setNull(4, Types.BIGINT);
      }
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getLong("id");
        }
      }
    }
    throw new SQLException("Failed to insert function");
  }

  public void commit() throws SQLException {
    this.connection.commit();
  }

  public void rollback() {
    try {
      this.connection.rollback();
    } catch (SQLException e) {
      Msg.error(this, "Failed to rollback transaction", e);
    }
  }

  public void close() {
    try {
      this.connection.close();
    } catch (SQLException e) {
      Msg.error(this, "Failed to close database connection", e);
    }
  }
}

// Signatures collected for a single function during ingest. 
// A function is only stored when it carries at a BSIM vector and/or a FIDB hash.
class FunctionSignatures {
  public String name;
  public FidHashQuad fidHash = null;   // FIDB signature (nullable)
  public String vectorSql = null;      // BSIM vector serialized with LSHVector.saveSQL() (nullable)

  public FunctionSignatures(String name) {
    this.name = name;
  }

  public boolean hasSignature() {
    return this.fidHash != null || this.vectorSql != null;
  }
}

// --- Analyzer Script ---------------------------------------------------------

public class SightHouseAnalyzerScript extends GhidraScript {

  private static final int EXIT_CODE_ERROR = 1;

  private static List<Function> filterFunctionOnInstructionCount(Map<Function, Integer> counts, int min, int max) {
    List<Function> filtered = new ArrayList<>();
    for (Map.Entry<Function, Integer> entry: counts.entrySet()) {
      int instructionCount = entry.getValue();
      if (min <= instructionCount && (instructionCount <= max || max <= 0)) {
        filtered.add(entry.getKey());
      }
    }
    return filtered;
  }

  public boolean needAnalysis(String filePath) throws IOException {
    try (FileInputStream fis = new FileInputStream(filePath)) {
      byte[] header = new byte[16];
      int bytesRead = fis.read(header);
      if (bytesRead < 4) {
        return false;
      }

      // Check for ELF
      if (header[0] == 0x7F && header[1] == 'E' && header[2] == 'L' && header[3] == 'F') {
        return true;
      }

      // Check for PE
      if (header[0] == 'M' && header[1] == 'Z') {
        if (bytesRead >= 20 && header[0x3C] + 0x3C < bytesRead) {
          int peHeaderOffset = header[0x3C] + 0x3C;
          if (header[peHeaderOffset] == 'P' && header[peHeaderOffset + 1] == 'E' &&
              header[peHeaderOffset + 2] == 0x00 && header[peHeaderOffset + 3] == 0x00) {
            return true;
          }
        }
      }

      // Check for Mach-O
      if (header[0] == (byte) 0xCF && header[1] == (byte) 0xFA && header[2] == (byte) 0xED && header[3] == (byte) 0xFE) {
        return true;
      } else if (header[0] == (byte) 0xCE && header[1] == (byte) 0xFA && header[2] == (byte) 0xED && header[3] == (byte) 0xFE) {
        return true;
      }
    }
    return false;
  }


  // Read a string field from a JSON object, returning "" when absent or null.
  private static String jsonString(JsonObject obj, String key) {
    if (obj.has(key) && !obj.get(key).isJsonNull()) {
      return obj.get(key).getAsString();
    }
    return "";
  }

  // Ingest a program's BSIM + FIDB signatures into the SightHouse database.
  private void addProgramToSightHouseDatabase(Program prgm, SightHouseConfiguration config) throws Exception {
    BsimConfiguration bsim = config.getBsim();
    FidbConfiguration fidb = config.getFidb();
    if (bsim == null && fidb == null) {
      return; // nothing to ingest
    }

    // Project identity from the raw job metadata.
    String origin = "";
    String name = "";
    String version = "";
    String rawMetadata = config.getRawMetadata();
    if (rawMetadata != null) {
      JsonObject meta = new JsonParser().parse(rawMetadata).getAsJsonObject();
      origin = jsonString(meta, "origin");
      name = jsonString(meta, "name");
      version = jsonString(meta, "version");
    }

    // Program identity.
    String md5 = prgm.getExecutableMD5();
    String programName = prgm.getName();
    String languageId = prgm.getLanguageID().getIdAsString();

    // Count instructions once per function.
    Map<Function, Integer> instructionCounts = new LinkedHashMap<>();
    FunctionManager fman = prgm.getFunctionManager();
    Listing listing = prgm.getListing();
    AddressSpace space = prgm.getAddressFactory().getDefaultAddressSpace();
    for (Function f : fman.getFunctions(space.getMinAddress(), true)) {
      InstructionIterator instructions = listing.getInstructions(f.getBody(), true);
      int instructionCount = 0;
      while (instructions.hasNext()) {
        instructions.next();
        instructionCount++;
      }
      instructionCounts.put(f, instructionCount);
    }

    for (DatabaseConfiguration database : config.getDatabases()) {
      SightHouseDatabase db = null;
      try {
        Msg.info(this, String.format("Connecting to SightHouse database: %s", database.getUrl()));
        db = new SightHouseDatabase(database.getUrl(), database.getUsername(), database.getPassword());
        db.loadVectorWeights();

        long projectId = db.getOrInsertProject(origin, name, version);

        // Skip the whole binary if it is already ingested.
        Long existing = db.getProgramIdByMd5(md5);
        if (existing != null) {
          db.linkProjectProgram(projectId, existing);
          db.commit();
          Msg.info(this, "Program already ingested, linked to project: " + programName);
          continue;
        }

        int idArch = db.getOrInsertString("archtable", languageId);
        long programId = db.insertProgram(md5, programName, idArch);
        db.linkProjectProgram(projectId, programId);

        // Collect BSIM + FIDB signatures per function.
        Map<Address, FunctionSignatures> collected = new HashMap<>();
        if (fidb != null) {
          this.collectFidbSignatures(prgm, fidb, instructionCounts, collected);
        }
        if (bsim != null) {
          this.collectBsimSignatures(prgm, bsim, db.buildVectorFactory(), instructionCounts, collected);
        }

        // Insert every function that carries at least one signature.
        int inserted = 0;
        for (FunctionSignatures fsig : collected.values()) {
          if (!fsig.hasSignature()) {
            continue;
          }
          Long idFidb = null;
          if (fsig.fidHash != null) {
            idFidb = db.getOrInsertFidb(fsig.fidHash.getFullHash(), fsig.fidHash.getSpecificHash(),
              fsig.fidHash.getSpecificHashAdditionalSize(), fsig.fidHash.getCodeUnitSize());
          }
          Long idVector = null;
          if (fsig.vectorSql != null) {
            idVector = db.insertVector(fsig.vectorSql);
          }
          db.insertFunction(programId, fsig.name, idVector, idFidb);
          inserted += 1;
        }

        db.commit();
        Msg.info(this, String.format("%s: inserted %d function(s) into %s",
          programName, inserted, database.getUrl()));
      } catch (Exception e) {
        if (db != null) {
          db.rollback();
        }
        Msg.error(this, "Failed to ingest program into " + database.getUrl(), e);
      } finally {
        if (db != null) {
          db.close();
        }
      }
    }
  }

  // Hash the FID-eligible functions and attach the hash quad to the collected signatures.
  private void collectFidbSignatures(Program prgm, FidbConfiguration fidb,
      Map<Function, Integer> instructionCounts, Map<Address, FunctionSignatures> collected) throws Exception {
    List<Function> funcs = filterFunctionOnInstructionCount(instructionCounts,
      fidb.getMinNumberOfInstructions(), fidb.getMaxNumberOfInstructions());
    FidService service = new FidService();
    FidHasher hasher = service.getHasher(prgm);
    for (Function f : funcs) {
      // Skip thunks, external functions and functions without a real (symbol) name.
      if (f.isThunk() || functionIsExternal(f) || f.getSymbol().getSource() == SourceType.DEFAULT) {
        continue;
      }
      FidHashQuad quad = null;
      try {
        quad = hasher.hash(f);
      } catch (MemoryAccessException e) {
        Msg.warn(this, "FIDB: failed to hash " + f.getName() + ": " + e.getMessage());
      }
      if (quad == null) {
        continue;
      }
      getOrCreateSignatures(collected, f).fidHash = quad;
    }
  }

  // Generate BSIM vectors for the filtered functions and attach them to the collected signatures.
  private void collectBsimSignatures(Program prgm, BsimConfiguration bsim,
      LSHVectorFactory vectorFactory, Map<Function, Integer> instructionCounts,
      Map<Address, FunctionSignatures> collected) throws Exception {
    List<Function> funcs = filterFunctionOnInstructionCount(instructionCounts,
      bsim.getMinNumberOfInstructions(), bsim.getMaxNumberOfInstructions());
    if (funcs.isEmpty()) {
      return;
    }
    // GenSignatures only reports an address offset, so index the functions by it to map back.
    Map<Long, Function> byOffset = new HashMap<>();
    for (Function f : funcs) {
      byOffset.put(f.getEntryPoint().getOffset(), f);
    }

    GenSignatures gensig = new GenSignatures(false); // no call graph
    try {
      gensig.setVectorFactory(vectorFactory);
      gensig.openProgram(prgm, null, null, null, null, null);
      gensig.scanFunctions(funcs.iterator(), funcs.size(), monitor);
      DescriptionManager manager = gensig.getDescriptionManager();
      Iterator<FunctionDescription> it = manager.listAllFunctions();
      while (it.hasNext()) {
        FunctionDescription fd = it.next();
        SignatureRecord sigrec = fd.getSignatureRecord();
        if (sigrec == null) {
          continue;
        }
        Function f = byOffset.get(fd.getAddress());
        if (f == null) {
          continue;
        }
        LSHVector vec = sigrec.getLSHVector();
        if (!(vectorFactory.getSelfSignificance(vec) > 0.0)) {
          continue;
        }
        getOrCreateSignatures(collected, f).vectorSql = vec.saveSQL();
      }
    } finally {
      gensig.dispose();
    }
  }

  private static FunctionSignatures getOrCreateSignatures(
      Map<Address, FunctionSignatures> collected, Function f) {
    Address entry = f.getEntryPoint();
    FunctionSignatures fsig = collected.get(entry);
    if (fsig == null) {
      fsig = new FunctionSignatures(f.getName());
      collected.put(entry, fsig);
    }
    return fsig;
  }

  // Demangle every function name in place before signatures are collected.
  private void demangleProgram(Program prgm) {
    for (Function f : prgm.getFunctionManager().getFunctions(true)) {
      String mangled = f.getName();
      if (mangled == null) {
        continue;
      }
      int transaction = prgm.startTransaction("Demangle");
      try {
        DemanglerCmd cmd = new DemanglerCmd(f.getEntryPoint(), mangled, new DemanglerOptions());
        cmd.applyTo(prgm, monitor);
      } catch (Exception e) {
        // Demangling is best-effort; leave names that cannot be demangled untouched.
      } finally {
        prgm.endTransaction(transaction, true);
      }
    }
  }

  // Whether a function is external. Taken from
  // ghidra.feature.fid.service.FidServiceLibraryIngest.
  private static boolean functionIsExternal(Function function) {
    Memory mem = function.getProgram().getMemory();
    Address entryPoint = function.getEntryPoint();
    if (function.isExternal() || !mem.contains(entryPoint)) {
      return true;
    }
    MemoryBlock block = mem.getBlock(entryPoint);
    return block == null || !block.isInitialized() || block.isExternalBlock();
  }

  private int decompileFunctions(Program prgm) {
    FunctionManager functionManager = prgm.getFunctionManager();
    // Save program before analysis
    try {
      this.saveProgram(prgm);
    } catch (DuplicateFileException e) {
      Msg.info(this, "DecompileFunctions: program " + prgm.getName() + " already addded");
    } catch (Exception e) {
      e.printStackTrace();
      return 0;
    }

    for (Function f: functionManager.getFunctions(true)) {
      if (f.isThunk()) { continue; }
      int transaction = prgm.startTransaction("Disassemble");

      EntryPointAnalyzer analyzer = new EntryPointAnalyzer();
      MessageLog log = new MessageLog();
      try {
        analyzer.added(prgm, f.getBody(), monitor, log);
      } catch (CancelledException e) {
        e.printStackTrace();
      }

      prgm.endTransaction(transaction, true);
    }
    // Save program after analysis 
    try {
      this.saveProgram(prgm);
    } catch (Exception e) {
      e.printStackTrace();
      return 0;
    }
    return functionManager.getFunctionCount();
  }

  public void analyzeOneProgram(Path path, SightHouseConfiguration config) throws Exception {
    if (!this.needAnalysis(path.toAbsolutePath().toString())) {
      Msg.warn(this, "File format is unknown, skipping analysis");
      return;
    }
    Program pr = this.importFile(path.toFile());
    if (pr == null) {
      Msg.error(this, String.format("Fail to import program: Auto-Importer failed to import program '%s'. "+ 
                            "This is likely due to unsupported architecture!", path));
      return;
    } 
    // Open and analyze program
    this.openProgram(pr);
    this.decompileFunctions(pr);
    // Demangle symbol names before collecting signatures
    this.demangleProgram(pr);
    // Add signatures (BSIM + FIDB) to the database
    this.addProgramToSightHouseDatabase(pr, config);

    // https://github.com/NationalSecurityAgency/ghidra/issues/3570 possible memory leak inside ghidra
    for (Object consumer : pr.getConsumerList()) {
      pr.release(consumer);
    }
    this.closeProgram(pr);
  }

  public void analyzeMultipleProgram(String directory, SightHouseConfiguration config) throws Exception {
    java.nio.file.Path p = Paths.get(directory);
    if (Files.isRegularFile(p)) {
      // Analyze a simple program (only one entry)
      this.analyzeOneProgram(p, config);
      return;
    }

    for (java.nio.file.Path path : Files.list(p).toList()) {
      if (Files.isRegularFile(path)) {
        // Analyze a simple program
        this.analyzeOneProgram(path, config);
      }
      else if (Files.isDirectory(path)) {
        // Do recursive analysis
        this.analyzeMultipleProgram(path.toAbsolutePath().toString(), config);
      }
    }
  }

  @Override
  public void run() throws Exception {
    String configPath = askString("Enter the path to the analyzer configuration file", "Ok"); 
    try {
      // Read the configuration 
      Gson gson = new GsonBuilder().excludeFieldsWithModifiers(Modifier.TRANSIENT).create();
      SightHouseConfiguration config = gson.fromJson(new FileReader(configPath), SightHouseConfiguration.class);

      // Analyse all programs
      this.analyzeMultipleProgram(config.getDirectory(), config);
    } catch (Exception e) {
      e.printStackTrace();
      System.exit(EXIT_CODE_ERROR);
    }
  }

}
