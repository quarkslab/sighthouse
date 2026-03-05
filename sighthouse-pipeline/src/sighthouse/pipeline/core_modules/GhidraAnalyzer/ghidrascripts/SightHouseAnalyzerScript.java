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
import java.sql.Statement;
import java.sql.PreparedStatement;

import java.io.File;
import java.io.FileReader;
import java.io.FileInputStream;
import java.io.IOException;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.Map.Entry;
import java.util.HashMap;
import java.util.Iterator;

import java.net.URL;
import java.net.MalformedURLException;

// Ghidra imports
import ghidra.app.script.GhidraScript;
import ghidra.app.util.importer.MessageLog;
import ghidra.app.decompiler.DecompileException;
import ghidra.app.plugin.core.disassembler.EntryPointAnalyzer;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Program;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.mem.MemoryAccessException;
import ghidra.program.model.lang.Language;
import ghidra.program.model.lang.LanguageID;
import ghidra.program.model.lang.CompilerSpec;
import ghidra.program.model.lang.CompilerSpecID;
import ghidra.program.model.symbol.SourceType;
import ghidra.framework.model.DomainFile;
import ghidra.framework.protocol.ghidra.GhidraURL;
import ghidra.util.exception.CancelledException;    
import ghidra.util.exception.DuplicateFileException;
import ghidra.util.Msg;

// BSIM imports 
import generic.lsh.vector.LSHVectorFactory;
import ghidra.features.bsim.query.BSimClientFactory;
import ghidra.features.bsim.query.BSimServerInfo;
import ghidra.features.bsim.query.BSimServerInfo.DBType;
import ghidra.features.bsim.query.FunctionDatabase;
import ghidra.features.bsim.query.FunctionDatabase.BSimError;
import ghidra.features.bsim.query.FunctionDatabase.ErrorCategory;
import ghidra.features.bsim.query.FunctionDatabase.Status;
import ghidra.features.bsim.query.GenSignatures;
import ghidra.features.bsim.query.LSHException;
import ghidra.features.bsim.query.description.DatabaseInformation;
import ghidra.features.bsim.query.description.DescriptionManager;
import ghidra.features.bsim.query.protocol.InsertRequest;
import ghidra.features.bsim.query.protocol.QueryExeCount;
import ghidra.features.bsim.query.protocol.ResponseExe;

// System for defining BSIM password to use for database connection
import java.awt.Component;
import java.net.Authenticator;
import java.net.PasswordAuthentication;
import javax.security.auth.callback.*;
import ghidra.framework.remote.SSHSignatureCallback;
import ghidra.framework.client.ClientAuthenticator;
import ghidra.framework.client.ClientUtil;
import ghidra.framework.remote.AnonymousCallback;

// JSON imports
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonArray;
import java.lang.reflect.Modifier;

// --- Configuration Stuff -----------------------------------------------------

class SightHouseConfiguration {
  private String directory;
  private String metadata;
  private String format;
  private transient String filteredMetadata = null;
  private BsimConfiguration bsim;
  private FidbConfiguration fidb;

  // Getters and Setters
  public String getDirectory() { return directory; }
  public BsimConfiguration getBsim() { return bsim; }
  public FidbConfiguration getFidb() { return fidb; }

  public String getMetadata() throws Exception {
    // Prepare metadata
    if (this.filteredMetadata == null && this.metadata != null) {
      JsonParser parser = new JsonParser();
      JsonObject jsonMetadata = parser.parse(this.metadata).getAsJsonObject();

      if (format.equals("simple")) {
        JsonArray metadataArray = jsonMetadata.getAsJsonArray("metadata");
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < metadataArray.size(); i++) {
            JsonArray pair = metadataArray.get(i).getAsJsonArray();
            result.append(pair.get(0).getAsString()).append("@")
                  .append(pair.get(1).getAsString());
            if (i < metadataArray.size() - 1) result.append(", ");
        }
        this.filteredMetadata = result.toString();

      } else if (format.equals("json")) {
        JsonObject filteredJsonMetadata = new JsonObject();
        ArrayList<String> metadataTags = new ArrayList<String>();
        metadataTags.add("origin");
        metadataTags.add("metadata");
        for (String key : metadataTags) {
          if (jsonMetadata.has(key)) {
            filteredJsonMetadata.add(key, jsonMetadata.get(key));
          }
        } 
        if (filteredJsonMetadata.size() != 0) {
          this.filteredMetadata = filteredJsonMetadata.toString();
        }
      } else {
          throw new Exception("Invalid metadata format: '" + format + "'");
      }
    }
    return this.filteredMetadata;
  }
}

class BsimConfiguration {
  private int min_instructions = 10;    // Mininum number of instruction to filter function
  private int max_instructions = 0;     // Maximum number of instruction to filter function (No maximum by default)
  private List<DatabaseConfiguration> databases = null;

  // Getters and Setters
  public int getMinNumberOfInstructions() { return min_instructions; }
  public int getMaxNumberOfInstructions() { return max_instructions; }
  public List<DatabaseConfiguration> getDatabases() { return databases; }
}

class FidbConfiguration {
  private int min_instructions = 2;     // Mininum number of instruction to filter function
  private int max_instructions = 0;     // Maximum number of instruction to filter function (No maximum by default)
  private List<DatabaseConfiguration> databases = null;

  // Getters and Setters
  public int getMinNumberOfInstructions() { return min_instructions; }
  public int getMaxNumberOfInstructions() { return max_instructions; }
  public List<DatabaseConfiguration> getDatabases() { return databases; }
}

class SightHouseClientAuthenticator implements ClientAuthenticator {
  private String userID = ClientUtil.getUserName(); // default username
  private String password = null;
  private Authenticator authenticator = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
      Msg.info(this, "PasswordAuthentication requested for " + getRequestingURL());
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
  public char[] getNewPassword(Component parent, String serverInfo, String username) { return null; }
  public char[] getKeyStorePassword(String keystorePath, boolean passwordError) { return null; }
  public boolean isSSHKeyAvailable() { return false; }
  public boolean processSSHSignatureCallbacks(String serverName, NameCallback nameCb, SSHSignatureCallback sshCb) { return false; }
}

class DatabaseConfiguration {
  private String url;
  private String username;
  private String password;
  // This field dos not need to be serialized
  private transient SightHouseClientAuthenticator authenticator = null;

  // Getters and Setters
  public String getUrl() { return url; }
  public String getUsername() { return username; }
  public String getPassword() { return password; }
  public ClientAuthenticator getAuthenticator() {
    // Create the authenticator if does not already exists
    if (this.authenticator == null) {
      this.authenticator = new SightHouseClientAuthenticator();
      this.authenticator.setCredentials(this.username, this.password);
    }
    return this.authenticator;
  }
}

// --- Analyzer Script ---------------------------------------------------------

public class SightHouseAnalyzerScript extends GhidraScript {

  private static final int EXIT_CODE_ERROR = 1;

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

  private void addProgramToBSimDatabase(Program prgm, SightHouseConfiguration config) throws Exception { // throws LSHException, IOException, MalformedURLException, DecompileException {
    BsimConfiguration bsim = config.getBsim();
    if (bsim == null) {
      return; // Abort
    }
    // Get the metadata from the config
    String metadata = config.getMetadata(); 
    // First filter onces the functions to search for
    List<Function> funcs = filterFunctionOnInstructionCount(prgm, bsim.getMinNumberOfInstructions(), bsim.getMaxNumberOfInstructions());
    for (DatabaseConfiguration database: bsim.getDatabases()) {
      // Derive BSIM url and connect to the database
      ClientUtil.setClientAuthenticator(database.getAuthenticator());
      // Decompilation is done only on symbols function and not function inside
      FunctionDatabase querydb = null;
      try {
        Msg.info(this, String.format("Connecting to BSIM database: %s", database.getUrl()));
        BSimServerInfo serverInfo = new BSimServerInfo(BSimClientFactory.deriveBSimURL(database.getUrl()));
        querydb = BSimClientFactory.buildClient(serverInfo, false);
        if (!querydb.initialize()) {
          throw new IOException(querydb.getLastError().message);
        }
        DatabaseInformation dbInfo = querydb.getInfo();

        LSHVectorFactory vectorFactory = querydb.getLSHVectorFactory();
        GenSignatures gensig = null;
        try {
          gensig = new GenSignatures(dbInfo.trackcallgraph);
          gensig.setVectorFactory(vectorFactory);
          gensig.addExecutableCategories(dbInfo.execats);
          gensig.addFunctionTags(dbInfo.functionTags);
          gensig.addDateColumnName(dbInfo.dateColumnName);

          DomainFile dFile = prgm.getDomainFile();
          URL fileURL = dFile.getSharedProjectURL(null);
          if (fileURL == null) {
            fileURL = dFile.getLocalProjectURL(null);
          }
          if (fileURL == null) {
            Msg.info(this, "Cannot add signatures for prgm which has never been saved");
            return;
          }

          String path = GhidraURL.getProjectPathname(fileURL);
          // bsim adds the prgm name to the path so we need to remove the prgm name here
          int lastSlash = path.lastIndexOf('/');
          path = lastSlash == 0 ? "/" : path.substring(0, lastSlash);

          URL normalizedProjectURL = GhidraURL.getProjectURL(fileURL);
          String repo = normalizedProjectURL.toExternalForm();

          gensig.openProgram(prgm, metadata, null, null, repo, path);
          FunctionManager fman = prgm.getFunctionManager();

          Listing listing = prgm.getListing();
          List<Function> listbsimfuncs = filterFunctionOnInstructionCount(prgm, bsim.getMinNumberOfInstructions(), bsim.getMaxNumberOfInstructions());
          gensig.scanFunctions(listbsimfuncs.iterator(), listbsimfuncs.size(), monitor);
          DescriptionManager manager = gensig.getDescriptionManager();
				  if (manager.numFunctions() == 0) {
				  	Msg.warn(this, "Skipping Insert: " + 
				  		prgm.getName() + " contains no functions with bodies");
				  	return;
				  }

          // need to call sortCallGraph on each FunctionDescription
          // this de-dupes the list of callees for each function
          // without this there can be SQL errors due to inserting duplicate
          // entries into the callgraph table
          manager.listAllFunctions().forEachRemaining(fd -> fd.sortCallgraph());

          InsertRequest insertreq = new InsertRequest();
          insertreq.manage = manager;
          if (insertreq.execute(querydb) == null) {
            BSimError lastError = querydb.getLastError();
            if ((lastError.category == ErrorCategory.Format) ||
                (lastError.category == ErrorCategory.Nonfatal)) {
              Msg.info(this, "Skipping Insert: " + prgm.getName() + ": " + lastError.message);
              return;
            }
          }

          StringBuffer status = new StringBuffer(prgm.getName());
          status.append(" added to database ");
          status.append(dbInfo.databasename);
          status.append("\n\n");
          QueryExeCount exeCount = new QueryExeCount();
          ResponseExe countResponse = exeCount.execute(querydb);
          if (countResponse != null) {
            status.append(dbInfo.databasename);
            status.append(" contains ");
            status.append(countResponse.recordCount);
            status.append(" executables.");
          }
          else {
            status.append("null response from QueryExeCount");
          }
          Msg.info(this, status.toString());
        }
        finally {
          if (gensig != null) {
            gensig.dispose();
          }
        }
      }
      finally {
        if (querydb != null) {
          querydb.close();
        }
      }
    }

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
    // Add signature to the different databases/backends
    this.addProgramToBSimDatabase(pr, config);
    // @TODO: implement me 
    // this.addProgramToFidbDatabase(pr, config);

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
