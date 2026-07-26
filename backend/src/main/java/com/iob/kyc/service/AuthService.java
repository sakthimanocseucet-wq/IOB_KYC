package com.iob.kyc.service;

import com.iob.kyc.dto.ApiResponse;
import com.iob.kyc.dto.LoginRequest;
import com.iob.kyc.dto.RegisterRequest;
import com.iob.kyc.model.Employee;
import com.iob.kyc.model.OtpCode;
import com.iob.kyc.model.User;
import com.iob.kyc.repository.EmployeeRepository;
import com.iob.kyc.repository.OtpCodeRepository;
import com.iob.kyc.repository.UserRepository;
import com.iob.kyc.security.JwtTokenProvider;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Map;

@Service
public class AuthService {

    private final UserRepository userRepository;
    private final EmployeeRepository employeeRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider jwtTokenProvider;
    private final AuthenticationManager authenticationManager;
    private final OtpCodeRepository otpCodeRepository;
    private final OTPService otpService;

    public AuthService(UserRepository userRepository, EmployeeRepository employeeRepository,
                       PasswordEncoder passwordEncoder, JwtTokenProvider jwtTokenProvider,
                       AuthenticationManager authenticationManager, OtpCodeRepository otpCodeRepository,
                       OTPService otpService) {
        this.userRepository = userRepository;
        this.employeeRepository = employeeRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtTokenProvider = jwtTokenProvider;
        this.authenticationManager = authenticationManager;
        this.otpCodeRepository = otpCodeRepository;
        this.otpService = otpService;
    }

    // ====================== USER REGISTRATION ======================

    @Transactional
    public ApiResponse register(RegisterRequest request) {
        String passwordError = validateUserPassword(request.password());
        if (passwordError != null) {
            return ApiResponse.error(passwordError, 400);
        }

        if (userRepository.findByEmail(request.email()).isPresent()) {
            return ApiResponse.error("This email is already registered. Please login or use a different email.", 400);
        }

        // Check for duplicate phone number
        if (request.phone() != null && !request.phone().isEmpty() && userRepository.findByPhone(request.phone()).isPresent()) {
            return ApiResponse.error("This phone number is already registered. Please use a different number.", 400);
        }

        User user = User.builder()
                .firstName(request.firstName())
                .lastName(request.lastName())
                .email(request.email())
                .phone(request.phone())
                .passwordHash(passwordEncoder.encode(request.password()))
                .role("USER")
                .active(true)
                .locked(false)
                .failedAttempts(0)
                .build();

        userRepository.save(user);
        return ApiResponse.success("Registration successful. Please login.", Map.of("userId", user.getId()));
    }

    // ====================== USER LOGIN ======================

    @Transactional
    public ApiResponse login(LoginRequest request) {
        try {
            Authentication authentication = authenticationManager.authenticate(
                    new UsernamePasswordAuthenticationToken(request.email(), request.password())
            );

            UserDetails userDetails = (UserDetails) authentication.getPrincipal();
            String token = jwtTokenProvider.generateToken(userDetails);
            User user = userRepository.findByEmail(request.email()).orElse(null);

            var name = (user != null && user.getFirstName() != null ? user.getFirstName() : "")
                      + (user != null && user.getLastName() != null ? " " + user.getLastName() : "");
            name = name.trim();
            if (name.isEmpty()) name = request.email().split("@")[0];
            return ApiResponse.success("Login successful", Map.of(
                    "token", token,
                    "email", request.email(),
                    "userId", user != null ? user.getId() : null,
                    "firstName", user != null && user.getFirstName() != null ? user.getFirstName() : "",
                    "lastName", user != null && user.getLastName() != null ? user.getLastName() : "",
                    "name", name
            ));
        } catch (Exception e) {
            return ApiResponse.error("Invalid email or password", 401);
        }
    }

    // ====================== EMPLOYEE REGISTRATION ======================

    @Transactional
    public ApiResponse registerEmployee(RegisterRequest request) {
        String passwordError = validateEmployeePassword(request.password());
        if (passwordError != null) {
            return ApiResponse.error(passwordError, 400);
        }

        if (request.employeeId() == null || request.employeeId().isEmpty()) {
            return ApiResponse.error("Employee ID is required", 400);
        }

        if (employeeRepository.findByEmail(request.email()).isPresent()) {
            return ApiResponse.error("This email is already registered as an employee.", 400);
        }

        if (employeeRepository.findByEmployeeId(request.employeeId()).isPresent()) {
            return ApiResponse.error("This Employee ID is already taken.", 400);
        }

        Employee.Role role;
        try {
            role = Employee.Role.valueOf(request.role().toUpperCase());
        } catch (Exception e) {
            return ApiResponse.error("Invalid role. Must be ADMIN, MANAGER, or OFFICER", 400);
        }

        Employee employee = Employee.builder()
                .employeeId(request.employeeId())
                .firstName(request.firstName())
                .lastName(request.lastName())
                .email(request.email())
                .phone(request.phone())
                .passwordHash(passwordEncoder.encode(request.password()))
                .role(role)
                .active(true)
                .locked(false)
                .failedAttempts(0)
                .build();

        employeeRepository.save(employee);
        return ApiResponse.success("Employee account created successfully. Please login.",
                Map.of("employeeId", employee.getEmployeeId()));
    }

    // ====================== EMPLOYEE LOGIN ======================

    @Transactional
    public ApiResponse adminLogin(String employeeId, String password) {
        if (employeeId == null || employeeId.isEmpty() || password == null || password.isEmpty()) {
            return ApiResponse.error("Employee ID and password are required", 400);
        }

        Employee employee = employeeRepository.findByEmployeeId(employeeId).orElse(null);
        if (employee == null) {
            return ApiResponse.error("Invalid employee ID or password", 401);
        }

        if (!passwordEncoder.matches(password, employee.getPasswordHash())) {
            return ApiResponse.error("Invalid employee ID or password", 401);
        }

        if (!employee.isActive()) {
            return ApiResponse.error("Account is deactivated", 403);
        }

        if (employee.isLocked()) {
            return ApiResponse.error("Account is locked", 403);
        }

        employee.setLastLogin(LocalDateTime.now());
        employeeRepository.save(employee);

        UserDetails userDetails = new org.springframework.security.core.userdetails.User(
                employee.getEmail(),
                employee.getPasswordHash(),
                employee.isActive(),
                true, true, !employee.isLocked(),
                java.util.List.of(new org.springframework.security.core.authority.SimpleGrantedAuthority("ROLE_" + employee.getRole().name()))
        );

        String employeeName = ((employee.getFirstName() != null ? employee.getFirstName() : "")
                + (employee.getLastName() != null ? " " + employee.getLastName() : "")).trim();
        if (employeeName.isEmpty()) employeeName = employeeId;

        Map<String, String> claims = new java.util.HashMap<>();
        claims.put("employeeId", employee.getEmployeeId());
        claims.put("role", employee.getRole().name());
        claims.put("branchId", employee.getBranchId() != null ? employee.getBranchId() : "");
        claims.put("employeeName", employeeName);

        String token = jwtTokenProvider.generateToken(userDetails, claims);

        return ApiResponse.success("Login successful", Map.of(
                "token", token,
                "email", employee.getEmail(),
                "userId", employee.getId(),
                "employeeId", employeeId,
                "role", employee.getRole().name(),
                "branchId", employee.getBranchId() != null ? employee.getBranchId() : "",
                "employeeName", employeeName,
                "firstName", employee.getFirstName() != null ? employee.getFirstName() : "",
                "lastName", employee.getLastName() != null ? employee.getLastName() : ""
        ));
    }

    // ====================== OTP ======================

    @Transactional
    public ApiResponse generateOTP(String identifier) {
        return generateOTP(identifier, OtpCode.Purpose.KYC);
    }

    @Transactional
    public ApiResponse generateOTP(String identifier, OtpCode.Purpose purpose) {
        SecureRandom random = new SecureRandom();
        int otpInt = 100000 + random.nextInt(900000);
        String otpCode = String.valueOf(otpInt);

        OtpCode otp = OtpCode.builder()
                .identifier(identifier)
                .otpCode(passwordEncoder.encode(otpCode))
                .purpose(purpose)
                .used(false)
                .expiresAt(LocalDateTime.now().plusMinutes(5))
                .createdAt(LocalDateTime.now())
                .build();

        otpCodeRepository.save(otp);

        if (identifier.contains("@")) {
            otpService.sendOtpEmail(identifier, otpCode);
        } else {
            String phone = identifier.replaceAll("[^0-9+]", "");
            if (phone.length() >= 10) {
                otpService.sendOtpSms(phone, otpCode);
            }
        }

        return ApiResponse.success("OTP sent successfully", null);
    }

    @Transactional
    public ApiResponse verifyOTP(String identifier, String otp) {
        return verifyOTP(identifier, otp, OtpCode.Purpose.KYC);
    }

    @Transactional
    public ApiResponse verifyOTP(String identifier, String otp, OtpCode.Purpose purpose) {
        OtpCode storedOtp = otpCodeRepository
                .findTopByIdentifierAndPurposeAndUsedFalseAndExpiresAtAfterOrderByCreatedAtDesc(
                        identifier, purpose, LocalDateTime.now())
                .orElse(null);

        if (storedOtp == null) {
            return ApiResponse.error("OTP expired or not found", 400);
        }

        if (!passwordEncoder.matches(otp, storedOtp.getOtpCode())) {
            return ApiResponse.error("Invalid OTP", 400);
        }

        storedOtp.setUsed(true);
        otpCodeRepository.save(storedOtp);

        return ApiResponse.success("OTP verified successfully", null);
    }

    // ====================== PASSWORD VALIDATION ======================

    private String validateUserPassword(String password) {
        if (password == null || password.length() < 8) {
            return "Password must be at least 8 characters long";
        }
        if (!password.matches(".*[A-Z].*")) {
            return "Password must contain at least one uppercase letter";
        }
        if (!password.matches(".*[a-z].*")) {
            return "Password must contain at least one lowercase letter";
        }
        if (!password.matches(".*[0-9].*")) {
            return "Password must contain at least one number";
        }
        if (!password.matches(".*[!@#$%^&*()_+\\-=\\[\\]{};':\"\\\\|,.<>/?].*")) {
            return "Password must contain at least one special character (!@#$%^&*...)";
        }
        return null;
    }

    private String validateEmployeePassword(String password) {
        if (password == null || password.length() < 12) {
            return "Employee password must be at least 12 characters long";
        }
        if (!password.matches(".*[A-Z].*")) {
            return "Password must contain at least one uppercase letter";
        }
        if (!password.matches(".*[a-z].*")) {
            return "Password must contain at least one lowercase letter";
        }
        if (!password.matches(".*[0-9].*")) {
            return "Password must contain at least one number";
        }
        if (!password.matches(".*[!@#$%^&*()_+\\-=\\[\\]{};':\"\\\\|,.<>/?].*")) {
            return "Password must contain at least one special character (!@#$%^&*...)";
        }
        if (password.toLowerCase().contains("password")) {
            return "Password must not contain the word 'password'";
        }
        if (password.toLowerCase().contains("iob")) {
            return "Password must not contain the bank name";
        }
        return null;
    }

    // ====================== USER FORGOT PASSWORD ======================

    @Transactional
    public ApiResponse checkForgotPassword(String identifier) {
        if (identifier == null || identifier.isEmpty()) {
            return ApiResponse.error("Please enter your email or mobile number", 400);
        }

        boolean exists = false;
        if (identifier.contains("@")) {
            exists = userRepository.findByEmail(identifier).isPresent();
        } else {
            String phone = identifier.replaceAll("[^0-9]", "");
            exists = userRepository.findByPhone(phone).isPresent();
        }

        if (!exists) {
            return ApiResponse.error("No account found with this " + (identifier.contains("@") ? "email" : "mobile number"), 404);
        }

        return ApiResponse.success("Account found", Map.of("identifier", identifier));
    }

    @Transactional
    public ApiResponse resetPassword(String identifier, String newPassword) {
        if (identifier == null || identifier.isEmpty()) {
            return ApiResponse.error("Identifier is required", 400);
        }

        String passwordError = validateUserPassword(newPassword);
        if (passwordError != null) {
            return ApiResponse.error(passwordError, 400);
        }

        User user = null;
        if (identifier.contains("@")) {
            user = userRepository.findByEmail(identifier).orElse(null);
        } else {
            String phone = identifier.replaceAll("[^0-9]", "");
            user = userRepository.findByPhone(phone).orElse(null);
        }

        if (user == null) {
            return ApiResponse.error("Account not found", 404);
        }

        if (passwordEncoder.matches(newPassword, user.getPasswordHash())) {
            return ApiResponse.error("New password must be different from your current password", 400);
        }

        user.setPasswordHash(passwordEncoder.encode(newPassword));
        userRepository.save(user);

        return ApiResponse.success("Password reset successful", null);
    }

    // ====================== EMPLOYEE FORGOT PASSWORD ======================

    @Transactional
    public ApiResponse checkEmployeeForgotPassword(String identifier) {
        if (identifier == null || identifier.isEmpty()) {
            return ApiResponse.error("Please enter your email or mobile number", 400);
        }

        Employee employee = null;
        if (identifier.contains("@")) {
            employee = employeeRepository.findByEmail(identifier).orElse(null);
        } else {
            String phone = identifier.replaceAll("[^0-9]", "");
            employee = employeeRepository.findByPhone(phone).orElse(null);
        }

        if (employee == null) {
            return ApiResponse.error("No employee account found with this " + (identifier.contains("@") ? "email" : "mobile number"), 404);
        }

        return ApiResponse.success("Account found", Map.of("identifier", identifier));
    }

    @Transactional
    public ApiResponse resetEmployeePassword(String identifier, String newPassword) {
        if (identifier == null || identifier.isEmpty()) {
            return ApiResponse.error("Identifier is required", 400);
        }

        String passwordError = validateEmployeePassword(newPassword);
        if (passwordError != null) {
            return ApiResponse.error(passwordError, 400);
        }

        Employee employee = null;
        if (identifier.contains("@")) {
            employee = employeeRepository.findByEmail(identifier).orElse(null);
        } else {
            String phone = identifier.replaceAll("[^0-9]", "");
            employee = employeeRepository.findByPhone(phone).orElse(null);
        }

        if (employee == null) {
            return ApiResponse.error("Account not found", 404);
        }

        if (passwordEncoder.matches(newPassword, employee.getPasswordHash())) {
            return ApiResponse.error("New password must be different from your current password", 400);
        }

        employee.setPasswordHash(passwordEncoder.encode(newPassword));
        employeeRepository.save(employee);

        return ApiResponse.success("Password reset successful", null);
    }
}
