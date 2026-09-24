//Frontend script that will performs BSIM query 
//@author Fenrisfulsur, MadSquirrels  
//@category SightHouse
//@keybinding 
//@menupath 
//@toolbar 

// Java imports
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.PreparedStatement;

// File IO
import java.io.IOException;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.FileInputStream;
import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.StringWriter;
import java.io.PrintWriter;
import java.io.FileWriter;
import java.io.Writer;

// Data structures
import java.util.List;
import java.util.ArrayList;
import java.util.function.Predicate;
import java.util.Collection;
import java.util.Iterator;
import java.util.Map;
import java.util.Map.Entry;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Iterator;
import java.math.BigInteger;

// Ghidra imports
import ghidra.app.script.GhidraScript;
import ghidra.app.plugin.core.analysis.AutoAnalysisManager;
import ghidra.program.util.GhidraProgramUtilities;
import ghidra.util.Msg;
import org.apache.commons.lang3.StringUtils;

// Language & CompilerSpec API
import ghidra.program.model.lang.Register;
import ghidra.program.model.lang.Language;
import ghidra.program.model.lang.LanguageID;
import ghidra.program.model.lang.CompilerSpec;
import ghidra.program.model.lang.CompilerSpecDescription;
import ghidra.program.model.lang.LanguageCompilerSpecPair;
import ghidra.program.model.lang.LanguageDescription;
import ghidra.program.model.lang.LanguageNotFoundException;
import ghidra.program.util.DefaultLanguageService;

// Import API
import ghidra.app.util.Option;
import ghidra.app.util.opinion.LoaderTier;
import ghidra.app.util.opinion.Loaded;
import ghidra.app.util.opinion.LoadSpec;
import ghidra.app.util.opinion.LoadException;
import ghidra.app.util.opinion.LoadResults;
import ghidra.app.util.opinion.Loader;
import ghidra.app.util.opinion.AbstractProgramLoader;
import ghidra.app.util.importer.MessageLog;
import ghidra.util.exception.CancelledException;
import ghidra.util.exception.InvalidInputException;
import ghidra.util.exception.DuplicateNameException;
import ghidra.program.database.function.OverlappingFunctionException;
import ghidra.app.plugin.core.disassembler.EntryPointAnalyzer;
import ghidra.app.cmd.disassemble.DisassembleCommand;

// Memory API 
import ghidra.app.util.MemoryBlockUtils;
import ghidra.program.database.mem.FileBytes;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.mem.MemoryAccessException;

// Ghidra Model API
import ghidra.program.model.listing.Program;
import ghidra.program.model.listing.ProgramContext;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.ContextChangeException;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressFactory;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.address.AddressOverflowException;
import ghidra.program.model.util.AddressSetPropertyMap;
import ghidra.program.model.symbol.SymbolTable;
import ghidra.program.model.symbol.Symbol;
import ghidra.framework.model.Project;
import ghidra.framework.model.DomainObject;
import ghidra.util.task.TaskMonitor;
import ghidra.program.flatapi.FlatProgramAPI; 

// Filesystem API
import ghidra.formats.gfilesystem.FileSystemService;
import ghidra.formats.gfilesystem.FSRL;
import ghidra.app.util.bin.ByteProvider;

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

// JSON & API
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.lang.reflect.Modifier;
import java.io.BufferedReader;
import java.io.DataOutputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;

// --- Wrapper Class for interacting with frontend database --------------------

class SightHouseProgram {
  private long id;
  private String name;
  private long user;
  private String language;
  private long file;
  private String state;
  private List<SightHouseSection> sections; // Array of Section objects
  private transient Map<Long, SightHouseFunction> functionByAddress = null; // Map that speed up lookup 

  public SightHouseProgram(long id, String name, long user, String language, 
      long file, String state, List<SightHouseSection> sections) {

    this.id = id;
    this.name = name;
    this.user = user;
    this.language = language;
    this.file = file;
    this.state = state;
    this.sections = sections;
  }

  // Getters and Setters 
  public long getId() { return id; }
  public String getName() { return name; }
  public long getUser() { return user; }
  public String getLanguage() { return language; }
  public long getFile() { return file; }
  public String getState() { return state; }
  public List<SightHouseSection> getSections() { return sections; }

  private void checkCache() {
    if (this.functionByAddress == null) {
      // Map does not exists yet, create it
      this.functionByAddress = new HashMap<Long, SightHouseFunction>();
      for (SightHouseSection section : sections) {
        for (SightHouseFunction function: section.getFunctions()) {
          this.functionByAddress.put(section.getStart() + function.getOffset(), function);
        }
      }
    }
  }

  public SightHouseFunction getFunctionByAddr(long address) {
    this.checkCache();
    return this.functionByAddress.get(address);
  }

  public boolean addFunction(SightHouseFunction func) {
    this.checkCache();
    // First search for the function section
    SightHouseSection section = null;
    for (SightHouseSection s : this.sections) {
      if (s.getId() == func.getSection()) {
        section = s;
        break;
      }
    }
    // Add function to lookup table
    if (section != null) {
      section.getFunctions().add(func);
      this.functionByAddress.put(section.getStart() + func.getOffset(), func);
    } 
    return section != null;
  }

  public boolean addSection(SightHouseSection section) {
    this.checkCache();
    // First search for the function section
    for (SightHouseSection s : this.sections) {
      if (s.getId() == section.getId()) {
        return false; // Abort 
      }
    }
    this.sections.add(section);
    for (SightHouseFunction function: section.getFunctions()) {
      this.functionByAddress.put(section.getStart() + function.getOffset(), function);
    }
    return true;
  }
}

class SightHouseSection {
  private long id;
  private String name;
  private long program;
  private long file_offset;
  private long start;
  private long end;
  private String perms;
  private String kind;
  private List<SightHouseFunction> functions; // Array of Function objects

  // Constructor
  public SightHouseSection(long id, String name, long program, long file_offset, 
      long start, long end, String perms, String kind, List<SightHouseFunction> functions) {

    this.id = id;
    this.name = name;
    this.program = program;
    this.file_offset = file_offset;
    this.start = start;
    this.end = end;
    this.perms = perms;
    this.kind = kind;
    this.functions = functions;
  }

  // Getters
  public long getId() { return id; }
  public String getName() { return name; }
  public long getProgram() { return program; }
  public long getFileOffset() { return file_offset; }
  public long getStart() { return start; }
  public long getEnd() { return end; }
  public String getPerms() { return perms; }
  public String getKind() { return kind; }
  public List<SightHouseFunction> getFunctions() { return functions; }
  public long size() { return end - start; }
}

class SightHouseFunction {
  private long id;
  private String name;
  private long offset;
  private long section;
  private Map<String, Object> details;
  private List<SightHouseMatch> matches; // Array of Match objects

  public SightHouseFunction(long id, String name, long offset, long section, Map<String, Object> details, List<SightHouseMatch> matches) {
    this.id = id;
    this.name = name;
    this.offset = offset;
    this.section = section;
    this.details = details;
    this.matches = matches;
  }

  // Getters
  public long getId() { return id; }
  public void setId(long id) { this.id = id; }
  public String getName() { return name; }
  public long getOffset() { return offset; }
  public long getSection() { return section; }
  public Map<String, Object> getDetails() { return details; }
  public List<SightHouseMatch> getMatches() { return matches; }
}

class SightHouseMatch {
  private long id;
  private String name;
  private long function;
  private Map<String, Object> metadata;

  // Constructor
  public SightHouseMatch(long id, String name, long function, Map<String, Object> metadata) {
    this.id = id;
    this.name = name;
    this.function = function;
    this.metadata = metadata;
  }

  // Getters
  public long getId() { return id; }
  public String getName() { return name; }
  public long getFunction() { return function; }
  public Map<String, Object> getMetadata() { return metadata; }
}


// --- Configuration Stuff -----------------------------------------------------

class SightHouseConfiguration {
  private String file;
  private String output;
  private String error;
  private SightHouseProgram program;
  private List<DatabaseConfiguration> databases;
  private BsimConfiguration bsim;
  private FidbConfiguration fidb;
  private AnalysisOptions options;

  // Getters and Setters
  public String getFile() { return file; }
  public String getOutput() { return output; }
  public String getErrorLog() { return error; }
  public SightHouseProgram getProgram() { return program; }
  public List<DatabaseConfiguration> getDatabases() { return databases; }
  public BsimConfiguration getBsim() { return bsim; }
  public FidbConfiguration getFidb() { return fidb; }
  public AnalysisOptions getAnalysisOptions() { return options; }
}

class AnalysisOptions {
  private Boolean auto_analysis = false; // Disabled by default

  // Getters and Setters
  public Boolean doAutoAnalysis() { return auto_analysis; }
}

class BsimConfiguration {
  private int min_instructions = 10;    // Mininum number of instruction to filter function
  private int max_instructions = -1;    // Maximum number of instruction to filter function (No maximum by default)
  private int number_of_matches = 10;   // Max number of matches per function
  private double similarity = 0.7;      // Similarity threshold [0:1]
  private double confidence = 1.0;      // Confidence threshold [0:+inf]

  // Getters and Setters
  public int getMinNumberOfInstructions() { return min_instructions; }
  public int getMaxNumberOfInstructions() { return max_instructions; }
  public int getMaxNumberOfMatches() { return number_of_matches; }
  public double getConfidence() { return confidence; }
  public double getSimilarity() { return similarity; }
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
  private String user;
  private String password;

  // Getters and Setters
  public String getUrl() { return url; }
  public String getUsername() { return user; }
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

  public Integer getArchitectureId(String languageId) throws SQLException {
    return this.getStringId("archtable", languageId);
  }

  private Integer getStringId(String table, String value) throws SQLException {
    String sql = "SELECT id FROM " + table + " WHERE val = ?";
    try (PreparedStatement pstmt = this.connection.prepareStatement(sql)) {
      pstmt.setString(1, value);
      try (ResultSet rs = pstmt.executeQuery()) {
        if (rs.next()) {
          return rs.getInt("id");
        }
      }
    }
    return null;
  }

  // Find potential function names sharing the given hash, restricted to the same architecture.
  // When specificHash is non-null the match is "exact" (full + specific hash).
  public List<FidbMatch> findFidbMatches(long fullHash, Long specificHash, int idArch)
      throws SQLException {
    String sql = "SELECT f.name AS function_name, pr.origin AS origin, pr.name AS project_name, pr.version AS version " +
      "FROM fidb fb JOIN functions f ON f.id_fidb = fb.id JOIN program p ON p.id = f.id_program " +
      "JOIN project_program pp ON pp.id_program = p.id JOIN project pr ON pr.id = pp.id_project " +
      "WHERE fb.full_hash = ? AND p.id_arch = ?";
    if (specificHash != null) {
      sql += " AND fb.specific_hash = ?";
    }
    List<FidbMatch> matches = new ArrayList<>();
    try (PreparedStatement pstmt = this.connection.prepareStatement(sql)) {
      pstmt.setLong(1, fullHash);
      pstmt.setInt(2, idArch);
      if (specificHash != null) {
        pstmt.setLong(3, specificHash);
      }
      try (ResultSet rs = pstmt.executeQuery()) {
        while (rs.next()) {
          matches.add(new FidbMatch(rs.getString("function_name"), rs.getString("origin"),
            rs.getString("project_name"), rs.getString("version")));
        }
      }
    }
    return matches;
  }

  // Nearest-neighbour vector search (Mirrors PostgresFunctionDatabase's query).
  public List<BsimMatch> queryNearest(String vectorSql, double similarity, double confidence, int max)
      throws SQLException {
    String sql =
      "WITH const(cvec) AS (VALUES (lshvector_in(CAST(? AS cstring)))), " +
      "comp AS (SELECT vt.id AS id, lshvector_compare(cvec, vt.vec) AS cfunc " +
      "         FROM const, vectable vt WHERE cvec % vt.vec) " +
      "SELECT f.name AS function_name, pr.origin AS origin, pr.name AS project_name, pr.version AS version, " +
      "       (comp.cfunc).sim AS sim, (comp.cfunc).sig AS sig " +
      "FROM comp " +
      "JOIN functions f ON f.id_vector = comp.id " +
      "JOIN program p ON p.id = f.id_program " +
      "JOIN project_program pp ON pp.id_program = p.id " +
      "JOIN project pr ON pr.id = pp.id_project " +
      "WHERE (comp.cfunc).sim > ? AND (comp.cfunc).sig > ? " +
      "ORDER BY (comp.cfunc).sim DESC LIMIT ?";
    List<BsimMatch> matches = new ArrayList<>();
    try (PreparedStatement pstmt = this.connection.prepareStatement(sql)) {
      pstmt.setString(1, vectorSql);
      pstmt.setDouble(2, similarity);
      pstmt.setDouble(3, confidence);
      pstmt.setInt(4, max);
      try (ResultSet rs = pstmt.executeQuery()) {
        while (rs.next()) {
          matches.add(new BsimMatch(rs.getString("function_name"), rs.getString("origin"),
            rs.getString("project_name"), rs.getString("version"),
            rs.getDouble("sim"), rs.getDouble("sig")));
        }
      }
    }
    return matches;
  }

  public void close() {
    try {
      this.connection.close();
    } catch (SQLException e) {
      Msg.error(this, "Failed to close database connection", e);
    }
  }
}

class FidbMatch {
  private String functionName;
  private String origin;
  private String projectName;
  private String version;

  public FidbMatch(String functionName, String origin, String projectName, String version) {
    this.functionName = functionName;
    this.origin = origin;
    this.projectName = projectName;
    this.version = version;
  }

  public String getFunctionName() { return functionName; }
  public String getOrigin() { return origin; }
  public String getProjectName() { return projectName; }
  public String getVersion() { return version; }
}

class BsimMatch {
  private String functionName;
  private String origin;
  private String projectName;
  private String version;
  private double similarity;
  private double significance;

  public BsimMatch(String functionName, String origin, String projectName, String version,
      double similarity, double significance) {
    this.functionName = functionName;
    this.origin = origin;
    this.projectName = projectName;
    this.version = version;
    this.similarity = similarity;
    this.significance = significance;
  }

  public String getFunctionName() { return functionName; }
  public String getOrigin() { return origin; }
  public String getProjectName() { return projectName; }
  public String getVersion() { return version; }
  public double getSimilarity() { return similarity; }
  public double getSignificance() { return significance; }
}

// --- Custom Loader -----------------------------------------------------------

class SightHouseLoader extends AbstractProgramLoader {

  // Loader static variables
  public static final String SIGHTHOUSE_OPTION = "SightHouseProgram";

  // Stub that needs to be implemented by the loader
  @Override
  public String getName() { return "SightHouseLoader"; }
  @Override
  public LoaderTier getTier() { return LoaderTier.UNTARGETED_LOADER; }
  @Override
  public int getTierPriority() { return 100; }
  @Override
  public boolean supportsLoadIntoProgram() { return false; }
  @Override
  public Collection<LoadSpec> findSupportedLoadSpecs(ByteProvider provider) throws IOException { throw new IOException("Not implemented"); }

  private SightHouseProgram parseProgramOptions(List<Option> options) {
    // Utils method to parse options list
    if (options != null) {
      for (Option option : options) {
        String optName = option.getName();
        if (optName.equals(SIGHTHOUSE_OPTION)) {
          return (SightHouseProgram) option.getValue();
        }
      }
    }
    return null;
  }

  @Override
  protected void loadProgramInto(ByteProvider provider, LoadSpec loadSpec,
      List<Option> options, MessageLog log, Program prog, TaskMonitor monitor)
    throws IOException, LoadException, CancelledException {

    SightHouseProgram sg = parseProgramOptions(options);
    AddressSpace space = prog.getAddressFactory().getDefaultAddressSpace();
    System.out.println("Got Program: "+sg.getName());

    // Iterate over all the sections 
    for (SightHouseSection section : sg.getSections()) {
      // Skip empty section
      if (section.size() <= 0) {
        continue;
      }
      try {
        String perms = section.getPerms();
        // If file offset is inferior to 0 it means uninit data
        if (section.getFileOffset() >= 0) {
          FileBytes fileBytes = MemoryBlockUtils.createFileBytes(prog, provider, section.getFileOffset(), section.size(), monitor);
          // @TODO: handle overlay
          MemoryBlockUtils.createInitializedBlock(
              prog, 
              false, // isOverlay 
              section.getName(),
              space.getAddress(section.getStart()), // Addr
              fileBytes, 
              0, // offset
              section.size(), // size
              null, // comment
              "SightHouseLoader", // source
              perms.charAt(0) == 'R',
              perms.charAt(1) == 'W',
              perms.charAt(2) == 'X',
              log 
              );
        } else {
          MemoryBlockUtils.createUninitializedBlock(
              prog,
              false, // overlay
              section.getName(),
              space.getAddress(section.getStart()), // Addr
              section.size(), // length
              null,
              "SightHouseLoader",
              perms.charAt(0) == 'R',
              perms.charAt(1) == 'W',
              perms.charAt(2) == 'X',
              log 
              );
        }
      }
      catch (AddressOverflowException e) {
        throw new LoadException("Invalid address range specified for section '"+section.getName()+"': start:" + section.getStart() +
            ", length:" + section.size() + " - end address exceeds address space boundary!");
      } catch (ArrayIndexOutOfBoundsException e) {
        throw new LoadException("Index out of bound for section '"+section.getName()+"': start:" + section.getStart() +
            ", length:" + section.size() + ", offset: " + section.getFileOffset());
      }
    }

  }

  private void loadFunctions(Program program, List<Option> options, TaskMonitor monitor) {
    FlatProgramAPI api = new FlatProgramAPI(program, monitor); 
    int transactionID = program.startTransaction("Loading functions - " + program.getName());
    FunctionManager functionMgr = program.getFunctionManager();

    SightHouseProgram sg = parseProgramOptions(options);
    AddressSpace space = program.getAddressFactory().getDefaultAddressSpace();

    ProgramContext context = program.getProgramContext();
    Register thumbRegister = context.getRegister("TMode");

    // Iterate over all the sections 
    for (SightHouseSection section : sg.getSections()) {
      for (SightHouseFunction function : section.getFunctions()) {
        Address addr = space.getAddress(section.getStart() + function.getOffset());
        // Check for thumb function BEFORE creating the function
        Object thumb = function.getDetails().get("thumb");
        if (thumb != null && (Boolean)thumb) {
          try {
            context.setValue(thumbRegister, addr, addr, BigInteger.valueOf(1));
          }
          catch (ContextChangeException e) {
            e.printStackTrace();
          }
        }
        // Create function  
        api.createFunction(addr, function.getName());
      }
    }
    program.endTransaction(transactionID, true);
    System.out.println("Functions added #" + functionMgr.getFunctionCount());
  }

  @Override
  protected List<Loaded<Program>> loadProgram(ByteProvider provider, String programName,
      Project project, String programFolderPath, LoadSpec loadSpec, List<Option> options,
      MessageLog log, Object consumer, TaskMonitor monitor)
    throws IOException, CancelledException {

    LanguageCompilerSpecPair pair = loadSpec.getLanguageCompilerSpec();
    Language importerLanguage = getLanguageService().getLanguage(pair.languageID);
    CompilerSpec importerCompilerSpec =
      importerLanguage.getCompilerSpecByID(pair.compilerSpecID);

    // Pass base address as null so it won't be used
    Program prog = createProgram(provider, programName, null, getName(), importerLanguage,
        importerCompilerSpec, consumer);
    List<Loaded<Program>> loadedList =
      List.of(new Loaded<>(prog, programName, programFolderPath));

    boolean success = false;
    try {
      // Will end up calling loadProgramInto
      loadInto(provider, loadSpec, options, log, prog, monitor);
      loadFunctions(prog, options, monitor);
      // createDefaultMemoryBlocks(prog, importerLanguage, log);
      success = true;
      System.out.println("Program load successfully");
      return loadedList;
    }
    finally {
      if (!success) {
        release(loadedList, consumer);
      }
    }
  }
}


// --- Analyzer Script ---------------------------------------------------------

public class SightHouseFrontendScript extends GhidraScript {

  // General static variables
  private static final int EXIT_CODE_SUCCESS = 0; 
  private static final int EXIT_CODE_ERROR = 1; 

  // Analysis variables
  private static final String DECOMPILER_SWITCH_ANALYZER = "Decompiler Switch Analysis";
  private static final String AGGRESSIVE_INSTRUCTION_FINDER = "Aggressive Instruction Finder";

  // Match provenance.
  private static final String MATCH_KIND_BSIM = "bsim";
  private static final String MATCH_KIND_FIDB = "fidb";

  // FIDB is "almost" a byte match, so we set it's score to arbitrary high similarity/confidence
  // so it work out of the box with BobRoss algorithm.
  private static final double FIDB_SIMILARITY = 1.0;
  private static final double FIDB_EXACT_SIGNIFICANCE = 1000.0;
  private static final double FIDB_FULL_SIGNIFICANCE = 100.0;

  private Program importWithCustomLoader(File file, SightHouseProgram sg, Language language, CompilerSpec compilerSpec) throws Exception {

    // Use this method instead of AutoImporter.importFresh as it rely on the ClassSearcher 
    // to get the loader class. However, declaring a custom loader in the script will not 
    // be detected by the ClassSearcher.
    // 
    // This method is a shorter version of AutoImporter.importFresh

    // Check parameters
    if (sg == null || compilerSpec == null || language == null) {
      return null;
    }

    LanguageCompilerSpecPair lcs = new LanguageCompilerSpecPair(
        language.getLanguageID(),
        compilerSpec.getCompilerSpecID()
        );

    // Create our list of options containing only the SightHouseProgram, we have to pass it inside the 
    // options list as we can not change the prototype of the loader, nor the loadProgram/loadProgramInto
    // without having to rewrite more code
    List<Option> options = new ArrayList<Option>();
    options.add(new Option(SightHouseLoader.SIGHTHOUSE_OPTION, sg, SightHouseProgram.class, Loader.COMMAND_LINE_ARG_PREFIX + "-SightHouseProgram"));

    SightHouseLoader loader = new SightHouseLoader();
    // FSRL are path with added metadata
    FileSystemService fs = FileSystemService.getInstance();
    FSRL fsrl = fs.getLocalFSRL(file);
    // Create a provider from our file
    try (ByteProvider provider = fs.getByteProvider(fsrl, true, monitor)) {
      // Loader.load will end up calling loadProgram
      LoadResults<? extends DomainObject> loadResults = loader.load(
          provider,                             // ByteProvider 
          sg.getName(),                         // Program import name 
          state.getProject(),                   // Project to import into
          null,                                 // ProgramFolderPath  
          new LoadSpec(loader, 0, lcs, false),  // Loader specification
          options,                              // No option needed 
          new MessageLog(),                     // Dummy message log
          this,                                 // Consumer object 
          monitor                               // Monitor object
          );

      println("Load results: " + loadResults.size());
      println("Primary: " + loadResults.getPrimary().getClass());

      // Return the first program loaded (should have only one)
      if (loadResults.size() == 1 && loadResults.getPrimary().getDomainObject() instanceof Program program) {
        return program;
      } else {
        println("Loader fail to load");
      }
    }
    return null;
  }

  private boolean analyzeProgram(Program program, AnalysisOptions analysisOptions) {
    // Adapted from analyzeProgram of Ghidra/Features/Base/src/main/java/ghidra/app/util/headless/HeadlessAnalyzer.java. 
    AutoAnalysisManager mgr = AutoAnalysisManager.getAnalysisManager(program);
    mgr.initializeOptions();

    int txId = program.startTransaction("Analysis");

    // Disable DECOMPILER_SWITCH_ANALYZER as it take year to finish and it is not need has we already have the functions
    // See this issue to understand how to manage options: https://github.com/NationalSecurityAgency/ghidra/issues/893
    Map<String, String> options = getCurrentAnalysisOptionsAndValues(program);
    if (options.containsKey(DECOMPILER_SWITCH_ANALYZER)) {
      setAnalysisOption(program, DECOMPILER_SWITCH_ANALYZER, "false");
    }

    // The custom loader maps raw bytes with no entry point and no symbols. When
    // the SRE client supplied functions they already seed disassembly, but in
    // Auto mode (web / `analyze` CLI) there are none, so the default flow-based
    // analyzers have nowhere to start and identify nothing. Detect that case and
    // let Ghidra bootstrap code discovery on its own.
    boolean bootstrap =
        analysisOptions.doAutoAnalysis()
            && program.getFunctionManager().getFunctionCount() == 0;

    if (!analysisOptions.doAutoAnalysis()) {
      // Disable almost all analysis if auto_analysis
      for (Map.Entry<String, String> entry : options.entrySet()) {
        // Disable all boolean options that are enabled by default
        if (entry.getValue().equals("true")) {
          setAnalysisOption(program, entry.getKey(), "false");
        }
      }
    } else if (bootstrap && options.containsKey(AGGRESSIVE_INSTRUCTION_FINDER)) {
      // Off by default: sweeps undefined executable bytes for valid code, which
      // is how functions get found when there is no entry point to disassemble.
      setAnalysisOption(program, AGGRESSIVE_INSTRUCTION_FINDER, "true");
    }

    try {
      // Tell analyzers that all the addresses in the set should be re-analyzed when analysis runs.
      mgr.reAnalyzeAll(null);
      if (bootstrap) {
        // Give the analyzers a starting point by disassembling the executable
        // blocks ourselves; the aggressive finder then sweeps whatever is left.
        seedDisassembly(program);
      }
      println("ANALYZING all memory and code: " + program.getName());
      mgr.startAnalysis(TaskMonitor.DUMMY); // kick start

      println("REPORT: Analysis succeeded for file: " + program.getName());
      GhidraProgramUtilities.markProgramAnalyzed(program);
    }
    finally {
      program.endTransaction(txId, true);
    }
    return true;
  }

  // Kick-start disassembly at the beginning of every executable, initialized
  // block. Without an entry point the flow-based analyzers have nowhere to
  // start; seeding each block start (following flow, restricted to executable
  // memory) reaches everything reachable from there, and the aggressive
  // instruction finder picks up the rest.
  private void seedDisassembly(Program program) {
    AddressSet exec = new AddressSet();
    for (MemoryBlock block : program.getMemory().getBlocks()) {
      if (block.isExecute() && block.isInitialized()) {
        exec.addRange(block.getStart(), block.getEnd());
      }
    }
    if (exec.isEmpty()) {
      println("No executable memory to disassemble");
      return;
    }
    for (MemoryBlock block : program.getMemory().getBlocks()) {
      if (block.isExecute() && block.isInitialized()) {
        new DisassembleCommand(block.getStart(), exec, true).applyTo(program, monitor);
      }
    }
  }

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

  // Serialize a match's provenance into the JSON string stored under the "executable" metadata key,
  private static String buildExecutableJson(String origin, String name, String version) {
    JsonObject executable = new JsonObject();
    executable.addProperty("origin", origin);
    JsonArray metadata = new JsonArray();
    JsonArray entry = new JsonArray();
    entry.add(name);
    entry.add(version);
    metadata.add(entry);
    executable.add("metadata", metadata);
    return executable.toString();
  }

  private void searchBSimSignatures(SightHouseProgram newSg, Program program,
      Map<Function, Integer> instructionCounts, SightHouseConfiguration config) throws Exception {
    BsimConfiguration bsim = config.getBsim();
    if (bsim == null) {
      println("BSIM is disabled, skipping search");
      return; // Abort
    }
    List<Function> funcs = filterFunctionOnInstructionCount(instructionCounts, bsim.getMinNumberOfInstructions(), bsim.getMaxNumberOfInstructions());
    println("Start searching for BSIM among " + funcs.size() + " functions");
    if (funcs.isEmpty()) {
      println("No functions to search for, skipping BSIM search");
      return;
    }

    int added = 0;
    for (DatabaseConfiguration database: config.getDatabases()) {
      SightHouseDatabase db = null;
      try {
        db = new SightHouseDatabase(database.getUrl(), database.getUsername(), database.getPassword());
        db.loadVectorWeights();

        // Generate the query program's vectors.
        Map<Long, String> vectorByOffset = new HashMap<Long, String>();
        GenSignatures gensig = new GenSignatures(false);
        LSHVectorFactory factory = db.buildVectorFactory();
        try {
          gensig.setVectorFactory(factory);
          gensig.openProgram(program, null, null, null, null, null);
          gensig.scanFunctions(funcs.iterator(), funcs.size(), monitor);
          DescriptionManager manager = gensig.getDescriptionManager();
          Iterator<FunctionDescription> it = manager.listAllFunctions();
          while (it.hasNext()) {
            FunctionDescription fd = it.next();
            SignatureRecord sigrec = fd.getSignatureRecord();
            if (sigrec == null) {
              continue;
            }
            // Mirror Ghidra's queryNearestVector: skip any query
            // vector whose self-significance is below the significance threshold.
            LSHVector lshVector = sigrec.getLSHVector();
            if (factory.getSelfSignificance(lshVector) < bsim.getConfidence()) {
              continue;
            }
            vectorByOffset.put(fd.getAddress(), lshVector.saveSQL());
          }
        }
        finally {
          gensig.dispose();
        }

        // Query each function's vector for nearest neighbours.
        for (Map.Entry<Long, String> entry: vectorByOffset.entrySet()) {
          SightHouseFunction function = newSg.getFunctionByAddr(entry.getKey());
          if (function == null) {
            continue;
          }
          List<BsimMatch> matches = db.queryNearest(
              entry.getValue(), bsim.getSimilarity(), bsim.getConfidence(), bsim.getMaxNumberOfMatches());
          for (BsimMatch match: matches) {
            Map<String, Object> metadata = new HashMap<String, Object>();
            metadata.put("executable", buildExecutableJson(match.getOrigin(), match.getProjectName(), match.getVersion()));
            metadata.put("kind", MATCH_KIND_BSIM);
            metadata.put("similarity", match.getSimilarity());
            metadata.put("significance", match.getSignificance());
            function.getMatches().add(new SightHouseMatch(0, match.getFunctionName(), 0, metadata));
            ++added;
          }
        }
      }
      finally {
        if (db != null) {
          db.close();
        }
      }
    }
    println("Found " + added + " potential BSIM matches");
  }

  private void searchFidbSignatures(SightHouseProgram newSg, Program program,
      Map<Function, Integer> instructionCounts, SightHouseConfiguration config) throws Exception {
    FidbConfiguration fidb = config.getFidb();
    if (fidb == null) {
      println("FIDB is disabled, skipping search");
      return; // Abort
    }
    List<Function> funcs = filterFunctionOnInstructionCount(instructionCounts, fidb.getMinNumberOfInstructions(), fidb.getMaxNumberOfInstructions());
    println("Start searching for FIDB among " + funcs.size() + " functions");
    if (funcs.isEmpty()) {
      println("No functions to search for, skipping FIDB search");
      return;
    }

    String languageId = program.getLanguageID().getIdAsString();
    FidService service = new FidService();
    FidHasher hasher = service.getHasher(program);

    int added = 0;
    for (DatabaseConfiguration database: config.getDatabases()) {
      SightHouseDatabase db = null;
      try {
        db = new SightHouseDatabase(database.getUrl(), database.getUsername(), database.getPassword());
        // FID compares only within the same architecture (processor). If this DB does not know the
        // target's architecture, it holds no compatible library, so skip it. 
        Integer idArch = db.getArchitectureId(languageId);
        if (idArch == null) {
          println("FIDB: skipping " + database.getUrl() + " -- architecture '" + languageId +
              "' unknown to this database (no compatible signatures)");
          continue;
        }

        for (Function f: funcs) {
          // Skip thunks and external functions as they have no real body to hash.
          if (f.isThunk() || functionIsExternal(f)) {
            continue;
          }
          FidHashQuad quad = null;
          try {
            quad = hasher.hash(f);
          } catch (MemoryAccessException e) {
            continue;
          }
          if (quad == null) {
            continue;
          }
          SightHouseFunction function = newSg.getFunctionByAddr(f.getEntryPoint().getOffset());
          if (function == null) {
            continue;
          }

          // Prefer exact (full + specific) matches, fall back to full-hash matches.
          String mode = "exact";
          List<FidbMatch> matches = db.findFidbMatches(quad.getFullHash(), quad.getSpecificHash(), idArch);
          if (matches.isEmpty()) {
            mode = "full";
            matches = db.findFidbMatches(quad.getFullHash(), null, idArch);
          }
          boolean exact = mode.equals("exact");
          for (FidbMatch match: matches) {
            Map<String, Object> metadata = new HashMap<String, Object>();
            metadata.put("executable", buildExecutableJson(match.getOrigin(), match.getProjectName(), match.getVersion()));
            metadata.put("kind", MATCH_KIND_FIDB);
            metadata.put("mode", mode);
            metadata.put("similarity", FIDB_SIMILARITY);
            metadata.put("significance", exact ? FIDB_EXACT_SIGNIFICANCE : FIDB_FULL_SIGNIFICANCE);
            function.getMatches().add(new SightHouseMatch(0, match.getFunctionName(), 0, metadata));
            ++added;
          }
        }
      }
      finally {
        if (db != null) {
          db.close();
        }
      }
    }
    println("Found " + added + " potential FIDB matches");
  }

  private SightHouseProgram searchSignatures(Program program, SightHouseConfiguration config) throws Exception {
    SightHouseProgram sg = config.getProgram();
    FunctionManager fman = program.getFunctionManager();
    AddressSpace space = program.getAddressFactory().getDefaultAddressSpace();

    // @TODO: Handle overlay: if we choose to implement overlay, we will need to find a way 
    //  to distinguish between FunctionDescription from BSIM queries as two function could 
    //  have the same address and name. 
    //  A way of handling this, would be to handle this would be to do separate query per sections 

    // Create new Program
    SightHouseProgram newSg = new SightHouseProgram(
        sg.getId(), sg.getName(), sg.getUser(), sg.getLanguage(), sg.getFile(), sg.getState(), new ArrayList<SightHouseSection>() 
    );
    // Create new sections
    for (SightHouseSection section: sg.getSections()) { 
      newSg.addSection(new SightHouseSection(
            section.getId(), section.getName(), section.getProgram(), section.getFileOffset(), 
            section.getStart(), section.getEnd(), section.getPerms(), section.getKind(), new ArrayList<SightHouseFunction>()
      ));
    }

    println("Adding function to program");
    // Since we did not define an entry point to the program, use the minimum address 
    for (Function f: fman.getFunctions(space.getMinAddress(), true)) {
      // Iterate over all ghidra functions as AutoAnalysis may have discover new functions
      // We need to iterate on sections to find which section contains each function
      for (SightHouseSection section: newSg.getSections()) {
        long addr = f.getEntryPoint().getOffset();
        if (section.getStart() <= addr && addr < section.getEnd()) {
          // Check if the function was defined in the input data
          SightHouseFunction oldFunction = sg.getFunctionByAddr(addr);
          SightHouseFunction function = null;
          if (oldFunction == null) {
            function = new SightHouseFunction(
                0,                                 // Invalid ID 
                f.getName(),                       // Function name 
                addr - section.getStart(),         // Function offset 
                section.getId(),                   // Section 
                new HashMap<String, Object>(),     // Empty details 
                new ArrayList<SightHouseMatch>()   // Empty matches
                ); 
          } else {
            // Use our previous data except for matches
            function = new SightHouseFunction(
                oldFunction.getId(),               // Previous ID       
                oldFunction.getName(),             // Function name   
                oldFunction.getOffset(),           // Function offset 
                section.getId(),                   // Section         
                oldFunction.getDetails(),          // Use previous details (@WARN: this may create problems if program modify input data)   
                new ArrayList<SightHouseMatch>()   // Empty matches   
                );
          }
          // Add function to program (will handle link with sections)
          newSg.addFunction(function);
        }
      }
    }

    println("Search for similar functions");
    // Count instructions once per function.
    Map<Function, Integer> instructionCounts = new LinkedHashMap<>();
    for (Function f : fman.getFunctions(space.getMinAddress(), true)) {
      InstructionIterator instructions = program.getListing().getInstructions(f.getBody(), true);
      int instructionCount = 0;
      while (instructions.hasNext()) {
        instructions.next();
        instructionCount++;
      }
      instructionCounts.put(f, instructionCount);
    }
    searchFidbSignatures(newSg, program, instructionCounts, config);
    searchBSimSignatures(newSg, program, instructionCounts, config);
    return newSg;
  } 

  private SightHouseProgram processProgram(SightHouseConfiguration config) throws Exception {
      SightHouseProgram sg = config.getProgram(); 
      File inputFile = null;
      // Parse input file 
      try {
        inputFile = new File(config.getFile());
        inputFile = inputFile.getCanonicalFile();
      }
      catch (IOException e) {
        throw new Exception("Failed to get canonical form of: " + inputFile.getPath());
      }
      if (!inputFile.isFile()) {
        throw new Exception(inputFile.getPath() + " is not a valid file.");
      }

      // Try to parse the language ID defined by the program
      Language language = null;
      CompilerSpec compilerSpec = null;
      try {
        LanguageID langid = new LanguageID(sg.getLanguage());
        language = DefaultLanguageService.getLanguageService().getLanguage(langid);
        compilerSpec = language.getDefaultCompilerSpec();
      } catch (IllegalArgumentException e) {
        throw new Exception("Unsupported language: " + sg.getLanguage());
      }
      catch (LanguageNotFoundException e) {
        throw new Exception("Unsupported language: " + sg.getLanguage());
      }

      println("Using Language:"+language.toString());
      Program program = importWithCustomLoader(inputFile, sg, language, compilerSpec);
      if (program == null) {
        throw new Exception("Fail to load program '" + sg.getName() + "'");
      }

      if (!analyzeProgram(program, config.getAnalysisOptions())) {
        throw new Exception("Fail to analyze program '" + sg.getName() + "'");
      }
      this.saveProgram(program);

      SightHouseProgram newSg = searchSignatures(program, config);

      // https://github.com/NationalSecurityAgency/ghidra/issues/3570 possible memory leak inside ghidra
      for (Object consumer : program.getConsumerList()) {
        program.release(consumer);
      }
      closeProgram(program);

      return newSg;
  }

  public void run() throws Exception { 
    SightHouseConfiguration config = null;
    String configPath = askString("Enter the path to the frontend configuration file", "Ok"); 
    try {
      // Read the configuration 
      Gson gson = new GsonBuilder().excludeFieldsWithModifiers(Modifier.TRANSIENT).create();
      config = gson.fromJson(new FileReader(configPath), SightHouseConfiguration.class);
      SightHouseProgram result = processProgram(config);
      Writer writer = new FileWriter(config.getOutput());
      gson.toJson(result, writer);
      writer.flush(); // @important: flush data to file
      writer.close();
    } catch (Exception e) {
      // Print exception on stderr and logfile
      StringWriter sw = new StringWriter();
      PrintWriter pw = new PrintWriter(sw);
      e.printStackTrace(pw);
      println(sw.toString());
      e.printStackTrace();
      if (config != null && config.getErrorLog() != null) {
        Writer writer = new FileWriter(config.getErrorLog());
        writer.write("Analysis failed:\n" + sw.toString());
        writer.flush(); // @important: flush data to file
        writer.close();
      }
      System.exit(EXIT_CODE_ERROR);
    }
  }

}

