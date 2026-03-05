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

// Authenticator
import javax.security.auth.callback.ChoiceCallback;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import java.awt.Component;
import javax.security.auth.callback.*;
import java.util.ArrayList;
import ghidra.framework.remote.SSHSignatureCallback;
import ghidra.framework.client.ClientAuthenticator;
import ghidra.framework.client.ClientUtil;
import ghidra.framework.remote.AnonymousCallback;
import java.net.Authenticator;
import java.net.PasswordAuthentication;

// Data structures 
import java.util.List;
import java.util.ArrayList;
import java.util.function.Predicate;
import java.util.Collection;
import java.util.Iterator;
import java.util.Map;
import java.util.Map.Entry;
import java.util.HashMap;
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
// import ghidra.app.util.importer.SingleLoaderFilter;
// import ghidra.app.util.importer.LcsHintLoadSpecChooser;
// import ghidra.app.util.importer.OptionChooser;
// import ghidra.app.util.importer.AutoImporter;
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
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.ContextChangeException;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressFactory;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.address.AddressOverflowException;
import ghidra.program.model.util.AddressSetPropertyMap;
import ghidra.program.model.symbol.SourceType;
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

// BSIM
import java.net.URL;
import ghidra.features.bsim.query.BSimClientFactory;
import ghidra.features.bsim.query.BSimServerInfo;
import ghidra.features.bsim.query.BSimServerInfo.DBType;
import ghidra.features.bsim.query.FunctionDatabase;
import ghidra.features.bsim.query.FunctionDatabase.BSimError;
import ghidra.features.bsim.query.FunctionDatabase.ErrorCategory;
import ghidra.features.bsim.query.FunctionDatabase.Status;
import ghidra.features.bsim.query.GenSignatures;
import ghidra.features.bsim.query.LSHException;
import ghidra.features.bsim.query.description.DescriptionManager;
import ghidra.features.bsim.query.description.ExecutableRecord;
import ghidra.features.bsim.query.description.FunctionDescription;
import ghidra.features.bsim.query.protocol.InsertRequest;
import ghidra.features.bsim.query.protocol.QueryExeCount;
import ghidra.features.bsim.query.protocol.ResponseExe;
import ghidra.features.bsim.query.protocol.SimilarityResult;
import ghidra.features.bsim.query.protocol.QueryNearest;
import ghidra.features.bsim.query.protocol.ResponseNearest;
import ghidra.features.bsim.query.protocol.SimilarityNote;

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
  private BsimConfiguration bsim;

  // Getters and Setters
  public String getFile() { return file; }
  public String getOutput() { return output; }
  public String getErrorLog() { return error; }
  public SightHouseProgram getProgram() { return program; }
  public BsimConfiguration getBsim() { return bsim; }
}

class BsimConfiguration {
  private boolean enabled;
  private int min_instructions = 10;    // Mininum number of instruction to filter function
  private int max_instructions = 0;     // Maximum number of instruction to filter function (No maximum by default)
  private int number_of_matches = 10;   // Max number of matches per function 
  private double similarity = 0.7;       // Similarity threshold [0:1]  
  private double confidence = 1.0;       // Confidence threshold [0:+inf]
  private List<DatabaseConfiguration> databases = null;

  // Getters and Setters
  public boolean isEnabled() { return enabled; }
  public int getMinNumberOfInstructions() { return min_instructions; }
  public int getMaxNumberOfInstructions() { return max_instructions; }
  public int getMaxNumberOfMatches() { return number_of_matches; }
  public double getConfidence() { return confidence; }
  public double getSimilarity() { return similarity; }
  public List<DatabaseConfiguration> getDatabases() { return databases; }
}

class SightHouseClientAuthenticator implements ClientAuthenticator {
  private String userID = ClientUtil.getUserName(); // default user
  private String password = null;
  private Authenticator authenticator = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
      System.out.println("PasswordAuthentication requested for " + getRequestingURL());
      return new PasswordAuthentication(userID, password.toCharArray());
    }
  };

  public void setCredentials(String newUsername, String newPassword) {
    this.userID = newUsername;
    this.password = newPassword;
  }

  public Authenticator getAuthenticator() {
    return authenticator;
  }

  // Stub that need to be implemented but not used
  public boolean processPasswordCallbacks(String title, String serverType, String serverName, boolean allowUserNameEntry,
      NameCallback nameCb, PasswordCallback passCb, ChoiceCallback choiceCb,
      AnonymousCallback anonymousCb, String loginError) {
    return false;
  }
  public boolean promptForReconnect(Component parent, final String message) { return false; }
  public char[] getNewPassword(Component parent, String serverInfo, String user) { return null; }
  public char[] getKeyStorePassword(String keystorePath, boolean passwordError) { return null; }
  public boolean isSSHKeyAvailable() { return false; }
  public boolean processSSHSignatureCallbacks(String serverName, NameCallback nameCb, SSHSignatureCallback sshCb) { return false; }
}

class DatabaseConfiguration {
  private String url;
  private String user;
  private String password;
  // This field dos not need to be serialized
  private transient SightHouseClientAuthenticator authenticator = null;

  // Getters and Setters
  public String getUrl() { return url; }
  public String getUsername() { return user; }
  public String getPassword() { return password; }
  public ClientAuthenticator getAuthenticator() {
    // Create the authenticator if does not already exists
    if (this.authenticator == null) {
      this.authenticator = new SightHouseClientAuthenticator();
      this.authenticator.setCredentials(this.user, this.password);
    }
    return this.authenticator;
  }
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
        throw new LoadException("Invalid address range specified: start:" + section.getStart() +
            ", length:" + section.size() + " - end address exceeds address space boundary!");
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

  private boolean analyzeProgram(Program program) {
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

    try {
      // Tell analyzers that all the addresses in the set should be re-analyzed when analysis runs.
      mgr.reAnalyzeAll(null);
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

  private List<Function> filterFunctionOnInstructionCount(Program program, int min, int max) {
    // Return a list of function to search for 
    FunctionManager fman = program.getFunctionManager();
    Listing listing = program.getListing();
    List<Function> filtered = new ArrayList<>();
    AddressSpace space = program.getAddressFactory().getDefaultAddressSpace();

    // Since we did not define an entry point to the program, use the minimum address 
    for (Function f: fman.getFunctions(space.getMinAddress(), true)) {
      AddressSetView body = f.getBody();
      InstructionIterator instructionIterator = listing.getInstructions(body, true);

      // Count the number of instructions
      int instructionCount = 0;
      while (instructionIterator.hasNext()) {
        Instruction instruction = instructionIterator.next();
        instructionCount++;
      }
      // Filter by number of instruction inside the function
      if (min <= instructionCount && (instructionCount <= max || max == 0)) {
        filtered.add(f);
      }
    }

    return filtered; 
  }

  private void searchBSimSignatures(SightHouseProgram newSg, Program program, SightHouseConfiguration config) throws Exception {
    BsimConfiguration bsim = config.getBsim();
    if (!bsim.isEnabled()) {
      println("BSIM is disabled, skipping search");
      return; // Abort
    }
    int added = 0;
    // First filter onces the functions to search for
    List<Function> funcs = filterFunctionOnInstructionCount(program, bsim.getMinNumberOfInstructions(), bsim.getMaxNumberOfInstructions());
    println("Start searching for BSIM among " + funcs.size() + " functions");
    for (DatabaseConfiguration database: bsim.getDatabases()) {
      // Derive BSIM url and connect to the database
      ClientUtil.setClientAuthenticator(database.getAuthenticator());
      BSimServerInfo serverInfo = new BSimServerInfo(BSimClientFactory.deriveBSimURL(database.getUrl()));
      try (FunctionDatabase querydb = BSimClientFactory.buildClient(serverInfo, false)) {
        if (!querydb.initialize()) {
          throw new Exception(querydb.getLastError().message);
        }

        GenSignatures gensig = new GenSignatures(false);
        try {
          // Open program
          gensig.setVectorFactory(querydb.getLSHVectorFactory());
          gensig.openProgram(program, null, null, null, null, null);

          // Scan all the functions
          DescriptionManager manager = gensig.getDescriptionManager();
          gensig.scanFunctions(funcs.iterator(), funcs.size(), monitor);

          // Prepare query for the database
          QueryNearest query = new QueryNearest();
          query.manage = manager;
          query.max = bsim.getMaxNumberOfMatches();
          query.thresh = bsim.getSimilarity();
          query.signifthresh = bsim.getConfidence();

          // Send query and wait for response
          ResponseNearest response = query.execute(querydb);
          if (response == null) {
            throw new Exception(querydb.getLastError().message);
          }

          // Iterate over results
          Iterator<SimilarityResult> iter = response.result.iterator();
          while (iter.hasNext()) {
            SimilarityResult sim = iter.next();
            FunctionDescription base = sim.getBase();
            ExecutableRecord exe = base.getExecutableRecord();

            // Get function section 
            SightHouseFunction function = newSg.getFunctionByAddr(base.getAddress());

            // Iterate over matches
            Iterator<SimilarityNote> subiter = sim.iterator();
            while (subiter.hasNext()) {
              SimilarityNote note = subiter.next();
              FunctionDescription fdesc = note.getFunctionDescription();
              ExecutableRecord exerec = fdesc.getExecutableRecord();

              // Create our metadata
              Map<String, Object> metadata = new HashMap<String, Object>();
              metadata.put("executable", exerec.getNameExec());
              metadata.put("similarity", note.getSimilarity());
              metadata.put("significance", note.getSignificance());

              // Add a new matches
              function.getMatches().add(new SightHouseMatch(
                    0, fdesc.getFunctionName(), 0, metadata
              ));
              ++added;
            }
          }
        }
        finally {
          gensig.dispose();
        }
      }
    }
    println("Found " + added + " potential BSIM matches");
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
    searchBSimSignatures(newSg, program, config);
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

      if (!analyzeProgram(program)) {
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

