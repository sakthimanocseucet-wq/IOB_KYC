package com.iob.kyc.config;

import com.iob.kyc.model.Branch;
import com.iob.kyc.model.Employee;
import com.iob.kyc.model.KYCApplication;
import com.iob.kyc.repository.BranchRepository;
import com.iob.kyc.repository.EmployeeRepository;
import com.iob.kyc.repository.KYCApplicationRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Optional;

@Component
public class DataSeeder implements CommandLineRunner {

    private static final Logger logger = LoggerFactory.getLogger(DataSeeder.class);

    private final EmployeeRepository employeeRepository;
    private final BranchRepository branchRepository;
    private final KYCApplicationRepository kycApplicationRepository;
    private final PasswordEncoder passwordEncoder;

    public DataSeeder(EmployeeRepository employeeRepository, BranchRepository branchRepository,
                      KYCApplicationRepository kycApplicationRepository, PasswordEncoder passwordEncoder) {
        this.employeeRepository = employeeRepository;
        this.branchRepository = branchRepository;
        this.kycApplicationRepository = kycApplicationRepository;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    public void run(String... args) {
        try {
            logger.info("[DataSeeder] Running data seeder...");
            createIfNotExists("ADM001", "admin@iobank.com", "Admin", "User",
                    "+919876543210", Employee.Role.ADMIN, "Admin@1234");
            seedBranches();
            backfillBranchIds();
            logger.info("[DataSeeder] Total employees in DB: {}", employeeRepository.count());
        } catch (Exception e) {
            logger.error("[DataSeeder] Error seeding data", e);
        }
    }

    private void backfillBranchIds() {
        List<KYCApplication> apps = kycApplicationRepository.findAll();
        for (KYCApplication app : apps) {
            if ((app.getBranchId() == null || app.getBranchId().isEmpty()) && app.getIfscCode() != null && !app.getIfscCode().isEmpty()) {
                Optional<Branch> branch = branchRepository.findByIfscCode(app.getIfscCode());
                if (branch.isPresent()) {
                    app.setBranchId(branch.get().getBranchName());
                    kycApplicationRepository.save(app);
                    logger.info("[DataSeeder] Backfilled branchId for app {} -> {}", app.getId(), branch.get().getBranchName());
                }
            }
        }
    }

    private void seedBranches() {
        if (branchRepository.count() > 0) return;
        Object[][] branches = {
            // Tamil Nadu - Chennai
            {"BRANCH-001", "IOB Chennai Main Branch", "IOBA0000001", "123 Mount Road", "Chennai", "Tamil Nadu", "600002", "+914423456789", "chennai@iobank.com"},
            {"BRANCH-002", "IOB T. Nagar Branch", "IOBA0000002", "45 Usman Road, T. Nagar", "Chennai", "Tamil Nadu", "600017", "+914424567890", "tnagar@iobank.com"},
            {"BRANCH-003", "IOB Mylapore Branch", "IOBA0000003", "78 Luz Church Road", "Chennai", "Tamil Nadu", "600004", "+914425678901", "mylapore@iobank.com"},
            {"BRANCH-004", "IOB Adyar Branch", "IOBA0000004", "23 Lattice Bridge Road", "Chennai", "Tamil Nadu", "600020", "+914426789012", "adyar@iobank.com"},
            {"BRANCH-005", "IOB Anna Nagar Branch", "IOBA0000005", "56 2nd Avenue, Anna Nagar", "Chennai", "Tamil Nadu", "600040", "+914427890123", "annanagar@iobank.com"},
            {"BRANCH-006", "IOB Velachery Branch", "IOBA0000006", "89 Velachery Main Road", "Chennai", "Tamil Nadu", "600042", "+914428901234", "velachery@iobank.com"},
            {"BRANCH-011", "IOB Tambaram Branch", "IOBA0000011", "12 GST Road, Tambaram", "Chennai", "Tamil Nadu", "600045", "+914422901234", "tambaram@iobank.com"},
            {"BRANCH-012", "IOB Porur Branch", "IOBA0000012", "34 Porur Main Road", "Chennai", "Tamil Nadu", "600125", "+914422911234", "porur@iobank.com"},
            {"BRANCH-013", "IOB Sholinganallur Branch", "IOBA0000013", "56 OMR Road, Sholinganallur", "Chennai", "Tamil Nadu", "600119", "+914422921234", "sholinganallur@iobank.com"},
            {"BRANCH-014", "IOB Thiruvanmiyur Branch", "IOBA0000014", "78 Thiruvanmiyur Main Road", "Chennai", "Tamil Nadu", "600041", "+914422931234", "thiruvanmiyur@iobank.com"},
            {"BRANCH-015", "IOB Nungambakkam Branch", "IOBA0000015", "90 Nungambakkam High Road", "Chennai", "Tamil Nadu", "600034", "+914422941234", "nungambakkam@iobank.com"},
            {"BRANCH-016", "IOB T. Nagar South Branch", "IOBA0000016", "11 South Usman Road", "Chennai", "Tamil Nadu", "600018", "+914422951234", "tnagarsouth@iobank.com"},
            {"BRANCH-017", "IOB Kodambakkam Branch", "IOBA0000017", "22 Kodambakkam Road", "Chennai", "Tamil Nadu", "600024", "+914422961234", "kodambakkam@iobank.com"},
            {"BRANCH-018", "IOB Ashok Nagar Branch", "IOBA0000018", "33 Ashok Nagar Main Road", "Chennai", "Tamil Nadu", "600083", "+914422971234", "ashoknagar@iobank.com"},
            {"BRANCH-019", "IOB Guindy Branch", "IOBA0000019", "44 Guindy Road", "Chennai", "Tamil Nadu", "600032", "+914422981234", "guindy@iobank.com"},
            {"BRANCH-020", "IOB Meenambakkam Branch", "IOBA0000020", "55 Meenambakkam Road", "Chennai", "Tamil Nadu", "600073", "+914422991234", "meenambakkam@iobank.com"},
            {"BRANCH-021", "IOB Pallavaram Branch", "IOBA0000021", "66 Grand Southern Trunk Road", "Chennai", "Tamil Nadu", "600074", "+914423001234", "pallavaram@iobank.com"},
            {"BRANCH-022", "IOB Chrompet Branch", "IOBA0000022", "77 Chrompet Main Road", "Chennai", "Tamil Nadu", "600044", "+914423011234", "chrompet@iobank.com"},
            {"BRANCH-023", "IOB Ambattur Branch", "IOBA0000023", "88 Ambattur Industrial Estate Road", "Chennai", "Tamil Nadu", "600058", "+914423021234", "ambattur@iobank.com"},
            {"BRANCH-024", "IOB Avadi Branch", "IOBA0000024", "99 Avadi-Poonamallee Road", "Chennai", "Tamil Nadu", "600071", "+914423031234", "avadi@iobank.com"},
            {"BRANCH-025", "IOB Tiruvallur Branch", "IOBA0000025", "101 Tiruvallur Road", "Tiruvallur", "Tamil Nadu", "602001", "+914423041234", "tiruvallur@iobank.com"},
            {"BRANCH-026", "IOB Kancheepuram Branch", "IOBA0000026", "102 Kancheepuram Road", "Kancheepuram", "Tamil Nadu", "631501", "+914423051234", "kancheepuram@iobank.com"},
            {"BRANCH-027", "IOB Sriperumbudur Branch", "IOBA0000027", "103 Sriperumbudur Road", "Sriperumbudur", "Tamil Nadu", "602105", "+914423061234", "sriperumbudur@iobank.com"},
            {"BRANCH-028", "IOB Uthiramerur Branch", "IOBA0000028", "104 Uthiramerur Main Road", "Uthiramerur", "Tamil Nadu", "603202", "+914423071234", "uthiramerur@iobank.com"},
            // Tamil Nadu - Coimbatore
            {"BRANCH-030", "IOB Coimbatore Main Branch", "IOBA0000030", "105 Town Hall Road", "Coimbatore", "Tamil Nadu", "641002", "+914223081234", "coimbatore@iobank.com"},
            {"BRANCH-031", "IOB RS Puram Branch", "IOBA0000031", "106 RS Puram Main Road", "Coimbatore", "Tamil Nadu", "641002", "+914223091234", "rspuram@iobank.com"},
            {"BRANCH-032", "IOB Gandhipuram Branch", "IOBA0000032", "107 Gandhipuram Main Road", "Coimbatore", "Tamil Nadu", "641012", "+914223101234", "gandhipuram@iobank.com"},
            {"BRANCH-033", "IOB Peelamedu Branch", "IOBA0000033", "108 Peelamedu Main Road", "Coimbatore", "Tamil Nadu", "641004", "+914223111234", "peelamedu@iobank.com"},
            {"BRANCH-034", "IOB Sulur Branch", "IOBA0000034", "109 Sulur Main Road", "Sulur", "Tamil Nadu", "641402", "+914223121234", "sulur@iobank.com"},
            {"BRANCH-035", "IOB Mettupalayam Branch", "IOBA0000035", "110 Mettupalayam Road", "Mettupalayam", "Tamil Nadu", "641301", "+914223131234", "mettupalayam@iobank.com"},
            // Tamil Nadu - Madurai
            {"BRANCH-040", "IOB Madurai Main Branch", "IOBA0000040", "111 Town Hall Road", "Madurai", "Tamil Nadu", "625001", "+914523141234", "madurai@iobank.com"},
            {"BRANCH-041", "IOB KK Nagar Branch", "IOBA0000041", "112 KK Nagar Main Road", "Madurai", "Tamil Nadu", "625020", "+914523151234", "kknagar@iobank.com"},
            {"BRANCH-042", "IOB Anna Nagar Madurai Branch", "IOBA0000042", "113 Anna Nagar Main Road", "Madurai", "Tamil Nadu", "625020", "+914523161234", "annanagarmadurai@iobank.com"},
            // Tamil Nadu - Salem
            {"BRANCH-050", "IOB Salem Main Branch", "IOBA0000050", "114 Town Hall Road", "Salem", "Tamil Nadu", "636001", "+914273171234", "salem@iobank.com"},
            {"BRANCH-051", "IOB Fairlands Branch", "IOBA0000051", "115 Fairlands Main Road", "Salem", "Tamil Nadu", "636016", "+914273181234", "fairlands@iobank.com"},
            {"BRANCH-052", "IOB Surampatti Branch", "IOBA0000052", "116 Surampatti Main Road", "Salem", "Tamil Nadu", "636007", "+914273191234", "surampatti@iobank.com"},
            // Tamil Nadu - Trichy
            {"BRANCH-060", "IOB Trichy Main Branch", "IOBA0000060", "117 Town Hall Road", "Trichy", "Tamil Nadu", "620001", "+914313201234", "trichy@iobank.com"},
            {"BRANCH-061", "IOB Thillai Nagar Branch", "IOBA0000061", "118 Thillai Nagar Main Road", "Trichy", "Tamil Nadu", "620018", "+914313211234", "thillainagar@iobank.com"},
            {"BRANCH-062", "IOB Srirangam Branch", "IOBA0000062", "119 Srirangam Main Road", "Trichy", "Tamil Nadu", "620006", "+914313221234", "srirangam@iobank.com"},
            // Tamil Nadu - Tirunelveli
            {"BRANCH-070", "IOB Tirunelveli Main Branch", "IOBA0000070", "120 Town Hall Road", "Tirunelveli", "Tamil Nadu", "627001", "+914623231234", "tirunelveli@iobank.com"},
            {"BRANCH-071", "IOB Palayamkottai Branch", "IOBA0000071", "121 Palayamkottai Main Road", "Tirunelveli", "Tamil Nadu", "627002", "+914623241234", "palayamkottai@iobank.com"},
            // Tamil Nadu - Erode
            {"BRANCH-080", "IOB Erode Main Branch", "IOBA0000080", "122 Town Hall Road", "Erode", "Tamil Nadu", "638001", "+914243251234", "erode@iobank.com"},
            {"BRANCH-081", "IOB Bhavani Branch", "IOBA0000081", "123 Bhavani Main Road", "Bhavani", "Tamil Nadu", "638301", "+914243261234", "bhavani@iobank.com"},
            // Tamil Nadu - Tiruppur
            {"BRANCH-085", "IOB Tiruppur Main Branch", "IOBA0000085", "124 Town Hall Road", "Tiruppur", "Tamil Nadu", "641601", "+914213271234", "tiruppur@iobank.com"},
            {"BRANCH-086", "IOB Avinashi Branch", "IOBA0000086", "125 Avinashi Main Road", "Avinashi", "Tamil Nadu", "641401", "+914213281234", "avinashi@iobank.com"},
            // Tamil Nadu - Vellore
            {"BRANCH-090", "IOB Vellore Main Branch", "IOBA0000090", "126 Town Hall Road", "Vellore", "Tamil Nadu", "632001", "+914163291234", "vellore@iobank.com"},
            {"BRANCH-091", "IOB Katpadi Branch", "IOBA0000091", "127 Katpadi Main Road", "Vellore", "Tamil Nadu", "632007", "+914163301234", "katpadi@iobank.com"},
            // Tamil Nadu - Thoothukudi
            {"BRANCH-095", "IOB Thoothukudi Main Branch", "IOBA0000095", "128 Town Hall Road", "Thoothukudi", "Tamil Nadu", "628001", "+914613311234", "thoothukudi@iobank.com"},
            {"BRANCH-096", "IOB Kovilpatti Branch", "IOBA0000096", "129 Kovilpatti Main Road", "Kovilpatti", "Tamil Nadu", "628501", "+914613321234", "kovilpatti@iobank.com"},
            // Tamil Nadu - Dindigul
            {"BRANCH-098", "IOB Dindigul Main Branch", "IOBA0000098", "130 Town Hall Road", "Dindigul", "Tamil Nadu", "624001", "+914513331234", "dindigul@iobank.com"},
            // Tamil Nadu - Karur
            {"BRANCH-099", "IOB Karur Main Branch", "IOBA0000099", "131 Town Hall Road", "Karur", "Tamil Nadu", "639001", "+914324334123", "karur@iobank.com"},
            // Tamil Nadu - Thanjavur
            {"BRANCH-100", "IOB Thanjavur Main Branch", "IOBA0000100", "132 Town Hall Road", "Thanjavur", "Tamil Nadu", "613001", "+914362335123", "thanjavur@iobank.com"},
            {"BRANCH-101", "IOB Kumbakonam Branch", "IOBA0000101", "133 Kumbakonam Main Road", "Kumbakonam", "Tamil Nadu", "612001", "+914353336123", "kumbakonam@iobank.com"},
            // Tamil Nadu - Cuddalore
            {"BRANCH-102", "IOB Cuddalore Branch", "IOBA0000102", "134 Cuddalore Main Road", "Cuddalore", "Tamil Nadu", "607001", "+914142337123", "cuddalore@iobank.com"},
            {"BRANCH-103", "IOB Chidambaram Branch", "IOBA0000103", "135 Chidambaram Main Road", "Chidambaram", "Tamil Nadu", "608001", "+914144338123", "chidambaram@iobank.com"},
            // Tamil Nadu - Villupuram
            {"BRANCH-104", "IOB Villupuram Branch", "IOBA0000104", "136 Villupuram Main Road", "Villupuram", "Tamil Nadu", "605602", "+914146339123", "villupuram@iobank.com"},
            // Delhi
            {"BRANCH-007", "IOB Delhi Main Branch", "IOBA0000007", "10 Parliament Street", "New Delhi", "Delhi", "110001", "+911123456789", "delhi@iobank.com"},
            // Maharashtra
            {"BRANCH-008", "IOB Mumbai Main Branch", "IOBA0000008", "22 Horniman Circle", "Mumbai", "Maharashtra", "400001", "+912223456789", "mumbai@iobank.com"},
            // West Bengal
            {"BRANCH-010", "IOB Kolkata Main Branch", "IOBA0000010", "44 Dalhousie Square", "Kolkata", "West Bengal", "700001", "+913323456789", "kolkata@iobank.com"},
            // Telangana - Hyderabad
            {"BRANCH-110", "IOB Hyderabad Main Branch", "IOBA0000110", "137 Abids Road", "Hyderabad", "Telangana", "500001", "+914034012345", "hyderabad@iobank.com"},
            {"BRANCH-111", "IOB Ameerpet Branch", "IOBA0000111", "138 Ameerpet Main Road", "Hyderabad", "Telangana", "500016", "+914034022345", "ameerpet@iobank.com"},
            {"BRANCH-112", "IOB Kukatpally Branch", "IOBA0000112", "139 Kukatpally Main Road", "Hyderabad", "Telangana", "500072", "+914034032345", "kukatpally@iobank.com"},
            {"BRANCH-113", "IOB Dilsukhnagar Branch", "IOBA0000113", "140 Dilsukhnagar Main Road", "Hyderabad", "Telangana", "500060", "+914034042345", "dilsukhnagar@iobank.com"},
            {"BRANCH-114", "IOB Madhapur Branch", "IOBA0000114", "141 Madhapur Main Road", "Hyderabad", "Telangana", "500081", "+914034052345", "madhapur@iobank.com"},
            {"BRANCH-115", "IOB LB Nagar Branch", "IOBA0000115", "142 LB Nagar Main Road", "Hyderabad", "Telangana", "500074", "+914034062345", "lbnagar@iobank.com"},
            {"BRANCH-116", "IOB Secunderabad Branch", "IOBA0000116", "143 MG Road, Secunderabad", "Secunderabad", "Telangana", "500003", "+914034072345", "secunderabad@iobank.com"},
            {"BRANCH-117", "IOB Gachibowli Branch", "IOBA0000117", "144 Gachibowli Main Road", "Hyderabad", "Telangana", "500032", "+914034082345", "gachibowli@iobank.com"},
            {"BRANCH-118", "IOB Begumpet Branch", "IOBA0000118", "145 Begumpet Main Road", "Hyderabad", "Telangana", "500016", "+914034092345", "begumpet@iobank.com"},
            {"BRANCH-119", "IOB Tarnaka Branch", "IOBA0000119", "146 Tarnaka Main Road", "Hyderabad", "Telangana", "500007", "+914034102345", "tarnaka@iobank.com"},
            // Andhra Pradesh - Vijayawada
            {"BRANCH-120", "IOB Vijayawada Main Branch", "IOBA0000120", "147 MG Road", "Vijayawada", "Andhra Pradesh", "520001", "+918663411234", "vijayawada@iobank.com"},
            {"BRANCH-121", "IOB Governorpet Branch", "IOBA0000121", "148 Governorpet Main Road", "Vijayawada", "Andhra Pradesh", "520002", "+918663421234", "governorpet@iobank.com"},
            {"BRANCH-122", "IOB Bandar Road Branch", "IOBA0000122", "149 Bandar Road", "Vijayawada", "Andhra Pradesh", "520001", "+918663431234", "bandarroad@iobank.com"},
            // Andhra Pradesh - Visakhapatnam
            {"BRANCH-130", "IOB Visakhapatnam Main Branch", "IOBA0000130", "150 Beach Road", "Visakhapatnam", "Andhra Pradesh", "530001", "+918913441234", "vizag@iobank.com"},
            {"BRANCH-131", "IOB Dwaraka Nagar Branch", "IOBA0000131", "151 Dwaraka Nagar Main Road", "Visakhapatnam", "Andhra Pradesh", "530016", "+918913451234", "dwarakanagar@iobank.com"},
            {"BRANCH-132", "IOB MVP Colony Branch", "IOBA0000132", "152 MVP Colony Main Road", "Visakhapatnam", "Andhra Pradesh", "530017", "+918913461234", "mvpcolony@iobank.com"},
            {"BRANCH-133", "IOB Gajuwaka Branch", "IOBA0000133", "153 Gajuwaka Main Road", "Visakhapatnam", "Andhra Pradesh", "530026", "+918913471234", "gajuwaka@iobank.com"},
            // Andhra Pradesh - Tirupati
            {"BRANCH-140", "IOB Tirupati Main Branch", "IOBA0000140", "154 MG Road", "Tirupati", "Andhra Pradesh", "517501", "+918773481234", "tirupati@iobank.com"},
            {"BRANCH-141", "IOB Renigunta Branch", "IOBA0000141", "155 Renigunta Main Road", "Renigunta", "Andhra Pradesh", "517520", "+918773491234", "renigunta@iobank.com"},
            // Andhra Pradesh - Others
            {"BRANCH-150", "IOB Kadapa Main Branch", "IOBA0000150", "156 Kadapa Main Road", "Kadapa", "Andhra Pradesh", "516001", "+918562350123", "kadapa@iobank.com"},
            {"BRANCH-151", "IOB Kurnool Main Branch", "IOBA0000151", "157 Kurnool Main Road", "Kurnool", "Andhra Pradesh", "518001", "+918512351123", "kurnool@iobank.com"},
            {"BRANCH-152", "IOB Anantapur Main Branch", "IOBA0000152", "158 Anantapur Main Road", "Anantapur", "Andhra Pradesh", "515001", "+918554352123", "anantapur@iobank.com"},
            {"BRANCH-153", "IOB Guntur Main Branch", "IOBA0000153", "159 Guntur Main Road", "Guntur", "Andhra Pradesh", "522001", "+918633531234", "guntur@iobank.com"},
            {"BRANCH-154", "IOB Nellore Main Branch", "IOBA0000154", "160 Nellore Main Road", "Nellore", "Andhra Pradesh", "524001", "+918613541234", "nellore@iobank.com"},
            {"BRANCH-155", "IOB Rajahmundry Main Branch", "IOBA0000155", "161 Rajahmundry Main Road", "Rajahmundry", "Andhra Pradesh", "533101", "+918833551234", "rajahmundry@iobank.com"},
            {"BRANCH-156", "IOB Kakinada Main Branch", "IOBA0000156", "162 Kakinada Main Road", "Kakinada", "Andhra Pradesh", "533001", "+918843561234", "kakinada@iobank.com"},
            {"BRANCH-157", "IOB Eluru Main Branch", "IOBA0000157", "163 Eluru Main Road", "Eluru", "Andhra Pradesh", "534001", "+918813571234", "eluru@iobank.com"},
            // Karnataka - Bangalore
            {"BRANCH-009", "IOB Bangalore Main Branch", "IOBA0000009", "33 MG Road", "Bangalore", "Karnataka", "560001", "+918023456789", "bangalore@iobank.com"},
            {"BRANCH-160", "IOB MG Road Bangalore Branch", "IOBA0000160", "164 MG Road", "Bangalore", "Karnataka", "560001", "+918035812345", "mgroadblr@iobank.com"},
            {"BRANCH-161", "IOB Indiranagar Branch", "IOBA0000161", "165 100 Feet Road, Indiranagar", "Bangalore", "Karnataka", "560038", "+918035822345", "indiranagar@iobank.com"},
            {"BRANCH-162", "IOB Koramangala Branch", "IOBA0000162", "166 Koramangala Main Road", "Bangalore", "Karnataka", "560034", "+918035832345", "koramangala@iobank.com"},
            {"BRANCH-163", "IOB Jayanagar Branch", "IOBA0000163", "167 Jayanagar 4th Block", "Bangalore", "Karnataka", "560041", "+918035842345", "jayanagar@iobank.com"},
            {"BRANCH-164", "IOB HSR Layout Branch", "IOBA0000164", "168 HSR Layout Main Road", "Bangalore", "Karnataka", "560102", "+918035852345", "hsrlayout@iobank.com"},
            {"BRANCH-165", "IOB Whitefield Branch", "IOBA0000165", "169 Whitefield Main Road", "Bangalore", "Karnataka", "560066", "+918035862345", "whitefield@iobank.com"},
            {"BRANCH-166", "IOB Electronic City Branch", "IOBA0000166", "170 Electronic City Phase 1", "Bangalore", "Karnataka", "560100", "+918035872345", "electroniccity@iobank.com"},
            {"BRANCH-167", "IOB Rajajinagar Branch", "IOBA0000167", "171 Rajajinagar Main Road", "Bangalore", "Karnataka", "560010", "+918035882345", "rajajinagar@iobank.com"},
            {"BRANCH-168", "IOB Malleshwaram Branch", "IOBA0000168", "172 Malleshwaram Main Road", "Bangalore", "Karnataka", "560003", "+918035892345", "malleshwaram@iobank.com"},
            {"BRANCH-169", "IOB Basavanagudi Branch", "IOBA0000169", "173 Basavanagudi Main Road", "Bangalore", "Karnataka", "560004", "+918035902345", "basavanagudi@iobank.com"},
            {"BRANCH-170", "IOB JP Nagar Branch", "IOBA0000170", "174 JP Nagar Main Road", "Bangalore", "Karnataka", "560078", "+918035912345", "jpnagar@iobank.com"},
            {"BRANCH-171", "IOB Bannerghatta Road Branch", "IOBA0000171", "175 Bannerghatta Road", "Bangalore", "Karnataka", "560076", "+918035922345", "bannerghattaroad@iobank.com"},
            {"BRANCH-172", "IOB Hebbal Branch", "IOBA0000172", "176 Hebbal Main Road", "Bangalore", "Karnataka", "560024", "+918035932345", "hebbal@iobank.com"},
        };
        for (Object[] b : branches) {
            if (!branchRepository.existsByBranchId((String) b[0])) {
                branchRepository.save(Branch.builder()
                        .branchId((String) b[0]).branchName((String) b[1]).ifscCode((String) b[2])
                        .branchAddress((String) b[3]).branchCity((String) b[4]).branchState((String) b[5])
                        .branchPincode((String) b[6]).branchPhone((String) b[7]).branchEmail((String) b[8])
                        .active(true).build());
            }
        }
        logger.info("[DataSeeder] Seeded {} branches", branchRepository.count());
    }

    private void createIfNotExists(String empId, String email, String firstName, String lastName,
                                   String phone, Employee.Role role, String password) {
        if (employeeRepository.findByEmployeeId(empId).isPresent()) {
            logger.info("[DataSeeder] {} account already exists, skipping", empId);
            return;
        }
        Employee emp = Employee.builder()
                .employeeId(empId)
                .email(email)
                .firstName(firstName)
                .lastName(lastName)
                .phone(phone)
                .passwordHash(passwordEncoder.encode(password))
                .role(role)
                .active(true)
                .locked(false)
                .failedAttempts(0)
                .build();
        employeeRepository.save(emp);
        logger.info("[DataSeeder] Created {} account: {}", role, empId);
    }
}
