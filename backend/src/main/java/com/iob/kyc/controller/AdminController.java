package com.iob.kyc.controller;

import com.iob.kyc.model.AuditLog;
import com.iob.kyc.model.Employee;
import com.iob.kyc.model.FraudAlert;
import com.iob.kyc.model.KYCApplication;
import com.iob.kyc.model.QRVerificationResult;
import com.iob.kyc.model.User;
import com.iob.kyc.repository.AuditLogRepository;
import com.iob.kyc.repository.EmployeeRepository;
import com.iob.kyc.repository.FraudAlertRepository;
import com.iob.kyc.repository.KYCApplicationRepository;
import com.iob.kyc.repository.QRVerificationRepository;
import com.iob.kyc.security.JwtTokenProvider;
import com.iob.kyc.service.AuditLogService;
import com.iob.kyc.service.FraudDetectionService;
import com.iob.kyc.service.OTPService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.io.ByteArrayOutputStream;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    private final KYCApplicationRepository kycApplicationRepository;
    private final FraudAlertRepository fraudAlertRepository;
    private final FraudDetectionService fraudDetectionService;
    private final OTPService otpService;
    private final EmployeeRepository employeeRepository;
    private final PasswordEncoder passwordEncoder;
    private final QRVerificationRepository qrVerificationRepository;
    private final JwtTokenProvider jwtTokenProvider;
    private final AuditLogService auditLogService;
    private final AuditLogRepository auditLogRepository;

    @Value("${file.upload-dir:./uploads}")
    private String uploadBaseDir;

    public AdminController(KYCApplicationRepository kycApplicationRepository,
                           FraudAlertRepository fraudAlertRepository,
                           FraudDetectionService fraudDetectionService,
                           OTPService otpService,
                           EmployeeRepository employeeRepository,
                           PasswordEncoder passwordEncoder,
                           QRVerificationRepository qrVerificationRepository,
                           JwtTokenProvider jwtTokenProvider,
                           AuditLogService auditLogService,
                           AuditLogRepository auditLogRepository) {
        this.kycApplicationRepository = kycApplicationRepository;
        this.fraudAlertRepository = fraudAlertRepository;
        this.fraudDetectionService = fraudDetectionService;
        this.otpService = otpService;
        this.employeeRepository = employeeRepository;
        this.passwordEncoder = passwordEncoder;
        this.qrVerificationRepository = qrVerificationRepository;
        this.jwtTokenProvider = jwtTokenProvider;
        this.auditLogService = auditLogService;
        this.auditLogRepository = auditLogRepository;
    }

    // ============================================================
    // RBAC HELPER METHODS
    // ============================================================

    private Map<String, String> extractEmployeeInfo(HttpServletRequest request) {
        Map<String, String> info = new HashMap<>();
        String authHeader = request.getHeader("Authorization");
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            String token = authHeader.substring(7);
            try {
                String email = jwtTokenProvider.getUsernameFromToken(token);
                info.put("email", email);
                Employee emp = employeeRepository.findByEmail(email).orElse(null);
                if (emp != null) {
                    info.put("employeeId", emp.getEmployeeId());
                    info.put("employeeRole", emp.getRole().name());
                    info.put("branchId", emp.getBranchId() != null ? emp.getBranchId() : "");
                }
            } catch (Exception e) {
                // Token parsing failed - ignore, RBAC will still deny access
            }
        }
        return info;
    }

    private String getClientIp(HttpServletRequest request) {
        String xForwardedFor = request.getHeader("X-Forwarded-For");
        if (xForwardedFor != null && !xForwardedFor.isEmpty()) {
            return xForwardedFor.split(",")[0].trim();
        }
        String xRealIp = request.getHeader("X-Real-IP");
        if (xRealIp != null && !xRealIp.isEmpty()) {
            return xRealIp;
        }
        return request.getRemoteAddr();
    }

    private void audit(HttpServletRequest request, String action, String entityType,
                       String entityId, String details) {
        Map<String, String> empInfo = extractEmployeeInfo(request);
        String employeeId = empInfo.getOrDefault("employeeId", "UNKNOWN");
        String employeeRole = empInfo.getOrDefault("employeeRole", "UNKNOWN");
        String branchId = empInfo.getOrDefault("branchId", "");
        String clientIp = getClientIp(request);
        String userAgent = request.getHeader("User-Agent");
        auditLogService.log(employeeId, employeeRole, branchId, action, entityType, entityId, details, clientIp, userAgent);
    }

    // ============================================================
    // CREATE EMPLOYEE ACCOUNT (ADMIN only)
    // ============================================================

    @PostMapping("/create-account")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> createEmployeeAccount(@RequestBody Map<String, String> body,
                                                                     HttpServletRequest request) {
        Map<String, Object> response = new HashMap<>();
        String firstName = body.getOrDefault("firstName", "").trim();
        String lastName = body.getOrDefault("lastName", "").trim();
        String email = body.getOrDefault("email", "").trim();
        String phone = body.getOrDefault("phone", "").trim();
        String role = body.getOrDefault("role", "").trim().toUpperCase();
        String password = body.getOrDefault("password", "");

        if (firstName.isEmpty() || email.isEmpty() || role.isEmpty() || password.isEmpty()) {
            response.put("success", false);
            response.put("message", "First name, email, role, and password are required");
            return ResponseEntity.badRequest().body(response);
        }

        Employee.Role empRole;
        try {
            empRole = Employee.Role.valueOf(role);
        } catch (Exception e) {
            response.put("success", false);
            response.put("message", "Invalid role. Must be MANAGER or OFFICER");
            return ResponseEntity.badRequest().body(response);
        }

        if (empRole == Employee.Role.ADMIN) {
            response.put("success", false);
            response.put("message", "Cannot create admin accounts from here");
            return ResponseEntity.badRequest().body(response);
        }

        if (employeeRepository.existsByEmail(email)) {
            response.put("success", false);
            response.put("message", "Email already registered");
            return ResponseEntity.badRequest().body(response);
        }

        String empId = role.substring(0, 3) + String.format("%03d", employeeRepository.count() + 1);
        String branchId = body.getOrDefault("branchId", "").trim();

        Employee emp = Employee.builder()
                .employeeId(empId)
                .firstName(firstName)
                .lastName(lastName)
                .email(email)
                .phone(phone)
                .passwordHash(passwordEncoder.encode(password))
                .role(empRole)
                .branchId(branchId.isEmpty() ? null : branchId)
                .active(true)
                .locked(false)
                .failedAttempts(0)
                .build();
        employeeRepository.save(emp);

        audit(request, "CREATE_ACCOUNT", "EMPLOYEE", empId,
                "Created " + empRole + " account for " + email);

        response.put("success", true);
        response.put("message", empRole + " account created successfully");
        response.put("employeeId", empId);
        response.put("role", empRole.name());
        return ResponseEntity.ok(response);
    }

    // ============================================================
    // RESET PASSWORD (ADMIN only)
    // ============================================================

    @PutMapping("/reset-password")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> resetEmployeePassword(@RequestBody Map<String, String> body,
                                                                     HttpServletRequest request) {
        Map<String, Object> response = new HashMap<>();
        String employeeId = body.getOrDefault("employeeId", "").trim();
        String newPassword = body.getOrDefault("newPassword", "").trim();

        if (employeeId.isEmpty() || newPassword.isEmpty()) {
            response.put("success", false);
            response.put("message", "employeeId and newPassword are required");
            return ResponseEntity.badRequest().body(response);
        }

        Employee emp = employeeRepository.findByEmployeeId(employeeId).orElse(null);
        if (emp == null) {
            response.put("success", false);
            response.put("message", "Employee not found");
            return ResponseEntity.notFound().build();
        }

        emp.setPasswordHash(passwordEncoder.encode(newPassword));
        employeeRepository.save(emp);

        audit(request, "RESET_PASSWORD", "EMPLOYEE", employeeId,
                "Password reset for employee " + employeeId);

        response.put("success", true);
        response.put("message", "Password reset successfully for " + employeeId);
        return ResponseEntity.ok(response);
    }

    // ============================================================
    // LIST EMPLOYEES (ADMIN only)
    // ============================================================

    @GetMapping("/employees")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<List<Map<String, Object>>> listEmployees() {
        List<Employee> employees = employeeRepository.findAll();
        List<Map<String, Object>> result = new ArrayList<>();
        for (Employee emp : employees) {
            Map<String, Object> info = new HashMap<>();
            info.put("id", emp.getId());
            info.put("employeeId", emp.getEmployeeId());
            info.put("name", emp.getFirstName() + " " + emp.getLastName());
            info.put("email", emp.getEmail());
            info.put("phone", emp.getPhone());
            info.put("role", emp.getRole());
            info.put("branchId", emp.getBranchId());
            info.put("isActive", emp.isActive());
            result.add(info);
        }
        return ResponseEntity.ok(result);
    }

    // ============================================================
    // AUDIT LOGS (ADMIN only)
    // ============================================================

    @GetMapping("/audit-logs")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<List<AuditLog>> getAuditLogs() {
        LocalDateTime since = LocalDateTime.now().minusDays(30);
        List<AuditLog> logs = auditLogRepository.findRecentLogs(since);
        return ResponseEntity.ok(logs);
    }

    // ============================================================
    // LIST APPLICATIONS (RBAC filtered)
    // ============================================================

    @GetMapping("/applications")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER', 'OFFICER')")
    public ResponseEntity<Map<String, Object>> listApplications(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String type,
            HttpServletRequest request) {

        Map<String, String> empInfo = extractEmployeeInfo(request);
        String employeeId = empInfo.getOrDefault("employeeId", "");
        String employeeRole = empInfo.getOrDefault("employeeRole", "");
        String branchId = empInfo.getOrDefault("branchId", "");

        Page<KYCApplication> applications;
        if (type != null && !type.isEmpty()) {
            KYCApplication.ApplicationType appType = KYCApplication.ApplicationType.valueOf(type.toUpperCase());
            applications = kycApplicationRepository.findByApplicationType(appType, PageRequest.of(page, size));
        } else {
            applications = kycApplicationRepository.findAll(PageRequest.of(page, size));
        }

        List<KYCApplication> filtered;
        if ("ADMIN".equals(employeeRole)) {
            // ADMIN sees ALL applications
            filtered = applications.getContent();
        } else if ("MANAGER".equals(employeeRole)) {
            // MANAGER sees unassigned or assigned to their branch
            // TODO: Implement branch-based filtering once branch assignment is fully implemented
            // For now, show all applications (managers can see all)
            filtered = applications.getContent();
        } else {
            // OFFICER: only applications assigned to them or unassigned
            filtered = applications.getContent().stream()
                    .filter(app -> app.getReviewedBy() == null
                            || employeeId.equals(app.getReviewedBy().getEmployeeId()))
                    .collect(Collectors.toList());
        }

        Map<String, Object> response = new HashMap<>();
        response.put("applications", filtered);
        response.put("currentPage", applications.getNumber());
        response.put("totalItems", filtered.size());
        response.put("totalPages", applications.getTotalPages());

        // Find all duplicate fraud alerts across applications (mobile, email, ID proof, photo, IP)
        List<KYCApplication> allApps = kycApplicationRepository.findAll();
        List<Map<String, Object>> allDuplicates = new ArrayList<>();

        // Helper: group non-rejected apps by a field and find duplicates from different users
        java.util.function.Function<KYCApplication, String> mobileGetter = KYCApplication::getMobile;
        java.util.function.Function<KYCApplication, String> emailGetter = KYCApplication::getEmail;
        java.util.function.Function<KYCApplication, String> idGetter = KYCApplication::getOcrIdNumber;
        java.util.function.Function<KYCApplication, String> panGetter = KYCApplication::getOcrPanNumber;
        java.util.function.Function<KYCApplication, String> selfieGetter = KYCApplication::getSelfieFilePath;
        java.util.function.Function<KYCApplication, String> photoGetter = KYCApplication::getPhotoFilePath;
        java.util.function.Function<KYCApplication, String> ipGetter = KYCApplication::getIpAddress;

        String[][] fieldConfigs = {
            {"mobile", "Mobile Number"},
            {"email", "Email Address"},
            {"id_number", "Aadhaar / ID Number"},
            {"pan_number", "PAN Number"},
            {"selfie", "Selfie Photo"},
            {"photo", "Profile Photo"},
            {"ip_address", "IP Address"}
        };

        @SuppressWarnings("unchecked")
        java.util.function.Function<KYCApplication, String>[] getters = new java.util.function.Function[] {
            mobileGetter, emailGetter, idGetter, panGetter, selfieGetter, photoGetter, ipGetter
        };

        for (int f = 0; f < fieldConfigs.length; f++) {
            String fieldKey = fieldConfigs[f][0];
            String fieldLabel = fieldConfigs[f][1];
            java.util.function.Function<KYCApplication, String> getter = getters[f];

            Map<String, List<KYCApplication>> groups = new HashMap<>();
            for (KYCApplication app : allApps) {
                if (app.getStatus() == KYCApplication.Status.REJECTED) continue;
                String value = getter.apply(app);
                if (value != null && !value.trim().isEmpty()) {
                    // Skip default/invalid IPs for IP duplicate detection
                    if ("ip_address".equals(fieldKey) && ("0.0.0.0".equals(value.trim()) || "N/A".equals(value.trim()))) {
                        continue;
                    }
                    groups.computeIfAbsent(value.trim(), k -> new ArrayList<>()).add(app);
                }
            }
            for (Map.Entry<String, List<KYCApplication>> entry : groups.entrySet()) {
                if (entry.getValue().size() > 1) {
                    Set<String> userIds = new HashSet<>();
                    for (KYCApplication a : entry.getValue()) {
                        if (a.getUser() != null) userIds.add(String.valueOf(a.getUser().getId()));
                    }
                    if (userIds.size() > 1) {
                        Map<String, Object> alert = new HashMap<>();
                        alert.put("type", fieldKey);
                        alert.put("label", fieldLabel);
                        alert.put("value", entry.getKey());
                        alert.put("count", entry.getValue().size());
                        alert.put("applicationIds", entry.getValue().stream().map(KYCApplication::getId).collect(Collectors.toList()));
                        alert.put("userIds", new ArrayList<>(userIds));
                        allDuplicates.add(alert);
                    }
                }
            }
        }
        response.put("duplicates", allDuplicates);

        return ResponseEntity.ok(response);
    }

    // ============================================================
    // COMPARE APPLICATIONS (ADMIN, MANAGER, OFFICER)
    // ============================================================

    @GetMapping("/applications/{id}/compare/{otherId}")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER', 'OFFICER')")
    public ResponseEntity<Map<String, Object>> compareApplications(
            @PathVariable Long id, @PathVariable Long otherId) {
        KYCApplication oldApp = kycApplicationRepository.findByIdWithUser(id).orElse(null);
        KYCApplication newApp = kycApplicationRepository.findByIdWithUser(otherId).orElse(null);
        if (oldApp == null || newApp == null) return ResponseEntity.notFound().build();

        boolean nameChanged = !java.util.Objects.equals(oldApp.getOcrName(), newApp.getOcrName());
        boolean addressChanged = !java.util.Objects.equals(oldApp.getOcrAddress(), newApp.getOcrAddress());
        boolean idChanged = !java.util.Objects.equals(oldApp.getOcrIdNumber(), newApp.getOcrIdNumber());
        boolean panChanged = !java.util.Objects.equals(oldApp.getOcrPanNumber(), newApp.getOcrPanNumber());
        boolean dobChanged = !java.util.Objects.equals(oldApp.getOcrDob(), newApp.getOcrDob());
        boolean mobileChanged = !java.util.Objects.equals(oldApp.getMobile(), newApp.getMobile());
        boolean emailChanged = !java.util.Objects.equals(oldApp.getEmail(), newApp.getEmail());

        return ResponseEntity.ok(Map.of(
                "old", oldApp,
                "new", newApp,
                "changes", Map.of(
                        "name", nameChanged,
                        "address", addressChanged,
                        "idNumber", idChanged,
                        "panNumber", panChanged,
                        "dob", dobChanged,
                        "mobile", mobileChanged,
                        "email", emailChanged,
                        "hasChanges", nameChanged || addressChanged || idChanged || panChanged || dobChanged || mobileChanged || emailChanged
                )
        ));
    }

    // ============================================================
    // PDF DOWNLOAD (ADMIN, MANAGER, OFFICER)
    // ============================================================

    @GetMapping("/applications/{id}/pdf")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER', 'OFFICER')")
    public ResponseEntity<byte[]> downloadKycPdf(@PathVariable Long id) {
        KYCApplication app = kycApplicationRepository.findByIdWithUser(id).orElse(null);
        if (app == null) return ResponseEntity.notFound().build();

        try {
            byte[] pdfBytes = generateAdminKycPdf(app);
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=KYC_" + app.getApplicationRef() + ".pdf")
                    .contentType(MediaType.APPLICATION_PDF)
                    .body(pdfBytes);
        } catch (Exception e) {
            return ResponseEntity.internalServerError().build();
        }
    }

    private byte[] generateAdminKycPdf(KYCApplication app) throws Exception {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        com.lowagie.text.Document document = new com.lowagie.text.Document(
                com.lowagie.text.PageSize.A4, 36, 36, 36, 36);
        com.lowagie.text.pdf.PdfWriter.getInstance(document, baos);
        document.open();

        com.lowagie.text.Font titleFont = com.lowagie.text.FontFactory.getFont(
                com.lowagie.text.FontFactory.HELVETICA_BOLD, 18, new java.awt.Color(0, 71, 171));
        com.lowagie.text.Font headerFont = com.lowagie.text.FontFactory.getFont(
                com.lowagie.text.FontFactory.HELVETICA_BOLD, 12, java.awt.Color.DARK_GRAY);
        com.lowagie.text.Font bodyFont = com.lowagie.text.FontFactory.getFont(
                com.lowagie.text.FontFactory.HELVETICA, 11, java.awt.Color.BLACK);
        com.lowagie.text.Font labelFont = com.lowagie.text.FontFactory.getFont(
                com.lowagie.text.FontFactory.HELVETICA_BOLD, 11, java.awt.Color.GRAY);
        java.time.format.DateTimeFormatter fmt = java.time.format.DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm a");

        document.add(new com.lowagie.text.Paragraph("IOB KYC - " + app.getApplicationType().name() + " Details", titleFont));
        document.add(new com.lowagie.text.Paragraph("Ref: " + app.getApplicationRef(), bodyFont));
        document.add(com.lowagie.text.Chunk.NEWLINE);

        document.add(new com.lowagie.text.Paragraph("Personal Information", headerFont));
        document.add(com.lowagie.text.Chunk.NEWLINE);

        com.lowagie.text.pdf.PdfPTable table = new com.lowagie.text.pdf.PdfPTable(2);
        table.setWidthPercentage(100);
        table.setWidths(new float[]{35, 65});
        table.setSpacingBefore(5);
        table.setSpacingAfter(5);

        addAdminRow(table, "Full Name", app.getOcrName(), labelFont, bodyFont);
        addAdminRow(table, "Date of Birth", app.getOcrDob() != null ? app.getOcrDob().format(fmt) : "--", labelFont, bodyFont);
        addAdminRow(table, "Aadhaar Number", app.getOcrIdNumber(), labelFont, bodyFont);
        addAdminRow(table, "PAN Number", app.getOcrPanNumber(), labelFont, bodyFont);
        addAdminRow(table, "Address", app.getOcrAddress(), labelFont, bodyFont);
        addAdminRow(table, "Application Type", app.getApplicationType().name(), labelFont, bodyFont);
        addAdminRow(table, "Status", app.getStatus().name(), labelFont, bodyFont);
        addAdminRow(table, "Submitted", app.getSubmittedAt() != null ? app.getSubmittedAt().format(fmt) : "--", labelFont, bodyFont);
        addAdminRow(table, "Reviewed", app.getReviewedAt() != null ? app.getReviewedAt().format(fmt) : "--", labelFont, bodyFont);
        addAdminRow(table, "Face Match", app.getFaceMatchPercentage() != null ? app.getFaceMatchPercentage() + "%" : "--", labelFont, bodyFont);
        addAdminRow(table, "Liveness", app.isLivenessPassed() ? "Passed" : "Failed", labelFont, bodyFont);
        addAdminRow(table, "Risk Level", app.getRiskLevel() != null ? app.getRiskLevel().name() : "LOW", labelFont, bodyFont);
        addAdminRow(table, "QR Verification", app.getQrVerificationStatus() != null ? app.getQrVerificationStatus().name() : "Not Performed", labelFont, bodyFont);
        if (app.getQrMatchPercentage() != null) {
            addAdminRow(table, "QR Match %", String.valueOf(app.getQrMatchPercentage()) + "%", labelFont, bodyFont);
        }
        document.add(table);

        document.add(com.lowagie.text.Chunk.NEWLINE);
        if (app.getReviewNotes() != null && !app.getReviewNotes().isEmpty()) {
            document.add(new com.lowagie.text.Paragraph("Review Notes: " + app.getReviewNotes(), bodyFont));
            document.add(com.lowagie.text.Chunk.NEWLINE);
        }
        document.add(new com.lowagie.text.Paragraph(
                "This document is system-generated. For official use only.",
                com.lowagie.text.FontFactory.getFont(com.lowagie.text.FontFactory.HELVETICA, 9, java.awt.Color.GRAY)));

        document.close();
        return baos.toByteArray();
    }

    private void addAdminRow(com.lowagie.text.pdf.PdfPTable table, String label, String value,
                              com.lowagie.text.Font labelFont, com.lowagie.text.Font bodyFont) {
        com.lowagie.text.pdf.PdfPCell labelCell = new com.lowagie.text.pdf.PdfPCell(
                new com.lowagie.text.Phrase(label, labelFont));
        labelCell.setPadding(8);
        labelCell.setBorderColor(java.awt.Color.LIGHT_GRAY);
        table.addCell(labelCell);
        com.lowagie.text.pdf.PdfPCell valueCell = new com.lowagie.text.pdf.PdfPCell(
                new com.lowagie.text.Phrase(value != null ? value : "--", bodyFont));
        valueCell.setPadding(8);
        valueCell.setBorderColor(java.awt.Color.LIGHT_GRAY);
        table.addCell(valueCell);
    }

    // ============================================================
    // GET SINGLE APPLICATION (RBAC filtered)
    // ============================================================

    @GetMapping("/applications/{id}")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER', 'OFFICER')")
    public ResponseEntity<?> getApplication(@PathVariable Long id,
                                            HttpServletRequest request) {
        Map<String, String> empInfo = extractEmployeeInfo(request);
        String employeeId = empInfo.getOrDefault("employeeId", "");
        String employeeRole = empInfo.getOrDefault("employeeRole", "");
        String branchId = empInfo.getOrDefault("branchId", "");

        return kycApplicationRepository.findByIdWithUser(id)
                .map(app -> {
                    // RBAC check
                    if ("ADMIN".equals(employeeRole)) {
                        return ResponseEntity.ok((Object) app);
                    } else if ("MANAGER".equals(employeeRole)) {
                        // TODO: Add branch-based filtering once branch assignment is implemented
                        // For now, managers can access any application
                        return ResponseEntity.ok((Object) app);
                    } else {
                        // OFFICER: only assigned or unassigned applications
                        if (app.getReviewedBy() == null
                                || employeeId.equals(app.getReviewedBy().getEmployeeId())) {
                            return ResponseEntity.ok((Object) app);
                        }
                        return ResponseEntity.status(403).body((Object) Map.of(
                                "success", false, "message", "Access denied: not assigned to this application"));
                    }
                })
                .orElse(ResponseEntity.notFound().build());
    }

    // ============================================================
    // APPROVE APPLICATION (ADMIN, MANAGER only)
    // ============================================================

    @PutMapping("/applications/{id}/approve")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER')")
    public ResponseEntity<Map<String, Object>> approveApplication(@PathVariable Long id,
                                                                  HttpServletRequest request) {
        Map<String, String> empInfo = extractEmployeeInfo(request);
        String employeeId = empInfo.getOrDefault("employeeId", "");

        return kycApplicationRepository.findByIdWithUser(id)
                .map(app -> {
                    Employee currentEmployee = employeeRepository.findByEmployeeId(employeeId).orElse(null);
                    app.setStatus(KYCApplication.Status.APPROVED);
                    app.setReviewedAt(LocalDateTime.now());
                    if (currentEmployee != null) {
                        app.setReviewedBy(currentEmployee);
                    }
                    if (app.getAccountNumber() == null || app.getAccountNumber().isEmpty()) {
                        app.setAccountNumber("IOB" + String.format("%04d", id) + String.format("%06d", System.currentTimeMillis() % 1000000));
                    }
                    if (app.getCustomerId() == null || app.getCustomerId().isEmpty()) {
                        app.setCustomerId("CUST" + String.format("%05d", id));
                    }
                    if (app.getIfscCode() == null || app.getIfscCode().isEmpty()) {
                        app.setIfscCode("IOBA000" + String.format("%04d", id));
                    }
                    kycApplicationRepository.save(app);

                    if (app.getApplicationType() == KYCApplication.ApplicationType.RE_KYC && app.getUser() != null) {
                        List<KYCApplication> userApps = kycApplicationRepository.findByUserIdOrderByIdDesc(app.getUser().getId());
                        for (KYCApplication oldApp : userApps) {
                            if (oldApp.getId() != app.getId()
                                    && oldApp.getStatus() == KYCApplication.Status.APPROVED
                                    && oldApp.getApplicationType() != KYCApplication.ApplicationType.RE_KYC) {
                                oldApp.setStatus(KYCApplication.Status.SUPERSEDED);
                                oldApp.setReviewNotes("Superseded by Re-KYC application " + app.getApplicationRef());
                                kycApplicationRepository.save(oldApp);
                                break;
                            }
                        }
                    }

                    User user = app.getUser();
                    if (user != null) {
                        String name = (user.getFirstName() != null ? user.getFirstName() : "")
                                + (user.getLastName() != null ? " " + user.getLastName() : "");
                        name = name.trim();
                        if (name.isEmpty()) name = "Customer";

                        if (user.getEmail() != null) {
                            otpService.sendKycApprovedEmail(user.getEmail(), name, app.getApplicationRef());
                        }
                    }

                    audit(request, "APPROVE_APPLICATION", "KYC_APPLICATION",
                            String.valueOf(id), "Approved application " + app.getApplicationRef());

                    Map<String, Object> response = new HashMap<>();
                    response.put("success", true);
                    response.put("message", "KYC application approved successfully");
                    return ResponseEntity.ok(response);
                })
                .orElse(ResponseEntity.notFound().build());
    }

    // ============================================================
    // REJECT APPLICATION (ADMIN, MANAGER only)
    // ============================================================

    @PutMapping("/applications/{id}/reject")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER')")
    public ResponseEntity<Map<String, Object>> rejectApplication(@PathVariable Long id,
                                                                  @RequestBody(required = false) Map<String, String> body,
                                                                  HttpServletRequest request) {
        Map<String, String> empInfo = extractEmployeeInfo(request);
        String employeeId = empInfo.getOrDefault("employeeId", "");

        return kycApplicationRepository.findByIdWithUser(id)
                .map(app -> {
                    Employee currentEmployee = employeeRepository.findByEmployeeId(employeeId).orElse(null);
                    app.setStatus(KYCApplication.Status.REJECTED);
                    app.setReviewedAt(LocalDateTime.now());
                    if (currentEmployee != null) {
                        app.setReviewedBy(currentEmployee);
                    }
                    String notes = null;
                    if (body != null && body.containsKey("notes")) {
                        notes = body.get("notes");
                        app.setReviewNotes(notes);
                    }
                    kycApplicationRepository.save(app);

                    User user = app.getUser();
                    if (user != null) {
                        String name = (user.getFirstName() != null ? user.getFirstName() : "")
                                + (user.getLastName() != null ? " " + user.getLastName() : "");
                        name = name.trim();
                        if (name.isEmpty()) name = "Customer";

                        if (user.getEmail() != null) {
                            otpService.sendKycRejectedEmail(user.getEmail(), name, app.getApplicationRef(), notes);
                        }
                    }

                    audit(request, "REJECT_APPLICATION", "KYC_APPLICATION",
                            String.valueOf(id), "Rejected application " + app.getApplicationRef()
                                    + (notes != null ? " — Reason: " + notes : ""));

                    Map<String, Object> response = new HashMap<>();
                    response.put("success", true);
                    response.put("message", "KYC application rejected");
                    return ResponseEntity.ok(response);
                })
                .orElse(ResponseEntity.notFound().build());
    }

    // ============================================================
    // DASHBOARD STATS (ADMIN, MANAGER, OFFICER)
    // ============================================================

    @GetMapping("/dashboard/stats")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER', 'OFFICER')")
    public ResponseEntity<Map<String, Object>> getDashboardStats() {
        Map<String, Object> stats = new HashMap<>();
        long total = kycApplicationRepository.count();
        long pending = kycApplicationRepository.countByStatus(KYCApplication.Status.PENDING);
        long approved = kycApplicationRepository.countByStatus(KYCApplication.Status.APPROVED);
        long rejected = kycApplicationRepository.countByStatus(KYCApplication.Status.REJECTED);
        long underReview = kycApplicationRepository.countByStatus(KYCApplication.Status.UNDER_REVIEW);
        stats.put("totalApplications", total);
        stats.put("pending", pending);
        stats.put("approved", approved);
        stats.put("rejected", rejected);
        stats.put("underReview", underReview);
        stats.put("pendingCount", pending);
        stats.put("approvedCount", approved);
        stats.put("rejectedCount", rejected);
        stats.put("highRiskCount", rejected);

        LocalDate today = LocalDate.now();
        LocalDateTime todayStart = today.atStartOfDay();
        LocalDateTime todayEnd = today.atTime(LocalTime.MAX);

        long todayTotal = kycApplicationRepository.countSubmittedSince(todayStart);
        long todayApproved = kycApplicationRepository.countByStatusSince(KYCApplication.Status.APPROVED, todayStart);
        long todayRejected = kycApplicationRepository.countByStatusSince(KYCApplication.Status.REJECTED, todayStart);
        long todayPending = kycApplicationRepository.countByStatusSince(KYCApplication.Status.PENDING, todayStart);

        stats.put("todayTotal", todayTotal);
        stats.put("todayApproved", todayApproved);
        stats.put("todayRejected", todayRejected);
        stats.put("todayPending", todayPending);

        LocalDate weekAgo = today.minusDays(6);
        List<Map<String, Object>> trends = new java.util.ArrayList<>();
        for (int i = 0; i < 7; i++) {
            LocalDate day = weekAgo.plusDays(i);
            LocalDateTime dayStart = day.atStartOfDay();
            LocalDateTime dayEnd = day.atTime(LocalTime.MAX);
            long dayTotal = kycApplicationRepository.countSubmittedSince(dayStart);
            Map<String, Object> dayData = new HashMap<>();
            dayData.put("date", day.toString());
            dayData.put("count", dayTotal);
            trends.add(dayData);
        }
        stats.put("dailyTrends", trends);

        return ResponseEntity.ok(stats);
    }

    // ============================================================
    // FRAUD ALERTS (ADMIN, MANAGER, OFFICER)
    // ============================================================

    @GetMapping("/fraud/alerts")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER', 'OFFICER')")
    public ResponseEntity<List<FraudAlert>> getFraudAlerts(
            @RequestParam(required = false) String severity,
            @RequestParam(required = false) String type,
            @RequestParam(required = false) Boolean resolved) {
        List<FraudAlert> alerts;
        if (severity != null) {
            alerts = fraudAlertRepository.findBySeverityOrderByCreatedAtDesc(FraudAlert.Severity.valueOf(severity.toUpperCase()));
        } else if (type != null) {
            alerts = fraudAlertRepository.findByAlertTypeOrderByCreatedAtDesc(FraudAlert.AlertType.valueOf(type.toUpperCase()));
        } else if (resolved != null) {
            alerts = fraudAlertRepository.findByResolvedOrderByCreatedAtDesc(resolved);
        } else {
            alerts = fraudAlertRepository.findByOrderByCreatedAtDesc();
        }
        return ResponseEntity.ok(alerts);
    }

    // ============================================================
    // FILE SERVING ENDPOINTS
    // ============================================================

    @GetMapping("/applications/{id}/selfie")
    public ResponseEntity<byte[]> getApplicationSelfie(@PathVariable Long id) {
        return serveFileField(id, KYCApplication::getSelfieFilePath);
    }

    @GetMapping("/applications/{id}/document")
    public ResponseEntity<byte[]> getApplicationDocument(@PathVariable Long id) {
        return serveFileField(id, KYCApplication::getDocFilePath);
    }

    @GetMapping("/applications/{id}/aadhaar-front")
    public ResponseEntity<byte[]> getAadhaarFront(@PathVariable Long id) {
        return serveFileField(id, KYCApplication::getAadhaarFrontPath);
    }

    @GetMapping("/applications/{id}/aadhaar-back")
    public ResponseEntity<byte[]> getAadhaarBack(@PathVariable Long id) {
        return serveFileField(id, KYCApplication::getAadhaarBackPath);
    }

    @GetMapping("/applications/{id}/pan-card")
    public ResponseEntity<byte[]> getPanCard(@PathVariable Long id) {
        return serveFileField(id, KYCApplication::getPanCardPath);
    }

    @GetMapping("/applications/{id}/photo")
    public ResponseEntity<byte[]> getApplicationPhoto(@PathVariable Long id) {
        return serveFileField(id, KYCApplication::getPhotoFilePath);
    }

    private ResponseEntity<byte[]> serveFileField(Long id, java.util.function.Function<KYCApplication, String> fieldGetter) {
        return kycApplicationRepository.findById(id)
                .map(app -> {
                    String filePath = fieldGetter.apply(app);
                    if (filePath == null || filePath.isEmpty()) {
                        return ResponseEntity.notFound().<byte[]>build();
                    }
                    try {
                        Path path = Paths.get(filePath);
                        org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(getClass());
                        if (!Files.exists(path)) {
                            String relativePath = filePath;
                            if (relativePath.startsWith("uploads/") || relativePath.startsWith("uploads\\")) {
                                relativePath = relativePath.substring("uploads/".length());
                            }
                            Path altPath = Paths.get(uploadBaseDir).toAbsolutePath().normalize().resolve(relativePath).normalize();
                            log.info("[Admin-Serve] '{}' not found, trying alt '{}' (exists={})", path.toAbsolutePath(), altPath, Files.exists(altPath));
                            if (Files.exists(altPath)) {
                                path = altPath;
                            } else {
                                log.warn("[Admin-Serve] File not found: original='{}', alt='{}', uploadBaseDir='{}'", filePath, altPath, uploadBaseDir);
                                return ResponseEntity.notFound().<byte[]>build();
                            }
                        }
                        byte[] imageBytes = Files.readAllBytes(path);
                        String contentType = Files.probeContentType(path);
                        if (contentType == null) contentType = MediaType.APPLICATION_OCTET_STREAM_VALUE;
                        return ResponseEntity.ok()
                                .header(HttpHeaders.CONTENT_TYPE, contentType)
                                .body(imageBytes);
                    } catch (Exception e) {
                        org.slf4j.LoggerFactory.getLogger(getClass()).error("[Admin-Serve] Error serving file: {}", e.getMessage(), e);
                        return ResponseEntity.internalServerError().<byte[]>build();
                    }
                })
                .orElse(ResponseEntity.notFound().build());
    }

    // ============================================================
    // QR CODE VERIFICATION (ADMIN, MANAGER, OFFICER)
    // ============================================================

    @GetMapping("/applications/{id}/qr-verify")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER', 'OFFICER')")
    public ResponseEntity<?> getQrVerificationResult(@PathVariable Long id) {
        java.util.Optional<QRVerificationResult> qrResult = qrVerificationRepository.findFirstByApplicationIdOrderByVerifiedAtDesc(id);
        KYCApplication app = kycApplicationRepository.findByIdWithUser(id).orElse(null);

        if (qrResult.isPresent()) {
            QRVerificationResult qr = qrResult.get();
            Map<String, Object> result = new HashMap<>();
            result.put("qrDetected", qr.isQrDetected());
            result.put("verificationStatus", qr.getVerificationStatus() != null ? qr.getVerificationStatus().name() : "SKIPPED");
            result.put("matchPercentage", qr.getMatchPercentage());
            result.put("documentType", qr.getDocumentType());
            result.put("verifiedAt", qr.getVerifiedAt());

            Map<String, Map<String, Object>> results = new java.util.LinkedHashMap<>();
            String ocrName = qr.getOcrName() != null && !qr.getOcrName().isEmpty() ? qr.getOcrName() : (app != null && app.getOcrName() != null ? app.getOcrName() : "");
            String ocrDob = qr.getOcrDob() != null && !qr.getOcrDob().isEmpty() ? qr.getOcrDob() : (app != null && app.getOcrDob() != null ? app.getOcrDob().toString() : "");
            String ocrId = qr.getOcrIdNumber() != null && !qr.getOcrIdNumber().isEmpty() ? qr.getOcrIdNumber() : (app != null && app.getOcrIdNumber() != null ? app.getOcrIdNumber() : "");
            String ocrPan = qr.getOcrPanNumber() != null && !qr.getOcrPanNumber().isEmpty() ? qr.getOcrPanNumber() : (app != null && app.getOcrPanNumber() != null ? app.getOcrPanNumber() : "");

            Map<String, Object> nameMap = new HashMap<>();
            nameMap.put("ocr", ocrName);
            nameMap.put("qr", qr.getQrName() != null ? qr.getQrName() : "");
            nameMap.put("match", qr.getNameMatch() != null && qr.getNameMatch());
            results.put("name", nameMap);

            Map<String, Object> dobMap = new HashMap<>();
            dobMap.put("ocr", ocrDob);
            dobMap.put("qr", qr.getQrDob() != null ? qr.getQrDob() : "");
            dobMap.put("match", qr.getDobMatch() != null && qr.getDobMatch());
            results.put("dob", dobMap);

            Map<String, Object> aadhaarMap = new HashMap<>();
            aadhaarMap.put("ocr", ocrId);
            aadhaarMap.put("qr", qr.getQrIdNumber() != null ? qr.getQrIdNumber() : "");
            aadhaarMap.put("match", qr.getIdNumberMatch() != null && qr.getIdNumberMatch());
            results.put("aadhaar_number", aadhaarMap);

            Map<String, Object> panMap = new HashMap<>();
            panMap.put("ocr", ocrPan);
            panMap.put("qr", qr.getQrPanNumber() != null ? qr.getQrPanNumber() : "");
            panMap.put("match", qr.getPanNumberMatch() != null && qr.getPanNumberMatch());
            results.put("pan_number", panMap);

            result.put("results", results);
            return ResponseEntity.ok(result);
        } else {
            return ResponseEntity.ok(java.util.Map.of(
                    "qrDetected", false,
                    "verificationStatus", "SKIPPED",
                    "message", "No QR verification performed"
            ));
        }
    }

    @PostMapping("/applications/{id}/qr-verify")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER', 'OFFICER')")
    public ResponseEntity<?> triggerQrVerificationAdmin(@PathVariable Long id,
                                                        HttpServletRequest request) {
        KYCApplication app = kycApplicationRepository.findByIdWithUser(id).orElse(null);
        if (app == null) return ResponseEntity.notFound().build();

        String imagePath = null;
        String docType = app.getDocType().name();

        if ("AADHAAR".equals(docType)) {
            imagePath = app.getAadhaarFrontPath();
            if (imagePath == null || imagePath.isEmpty()) {
                imagePath = app.getAadhaarBackPath();
            }
        } else if ("PAN".equals(docType)) {
            imagePath = app.getPanCardPath();
        }
        if (imagePath == null || imagePath.isEmpty()) {
            imagePath = app.getDocFilePath();
        }

        if (imagePath == null || imagePath.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("success", false, "message", "No document image uploaded"));
        }

        try {
            Path path = Paths.get(imagePath);
            if (!Files.exists(path)) {
                String relativePath = imagePath;
                if (relativePath.startsWith("uploads/")) {
                    relativePath = relativePath.substring("uploads/".length());
                } else if (relativePath.startsWith("uploads\\")) {
                    relativePath = relativePath.substring("uploads\\".length());
                }
                Path altPath = Paths.get(uploadBaseDir).resolve(relativePath).normalize();
                if (Files.exists(altPath)) {
                    path = altPath;
                } else {
                    return ResponseEntity.badRequest().body(Map.of("success", false, "message", "Document file not found"));
                }
            }

            byte[] imageBytes = Files.readAllBytes(path);
            org.springframework.core.io.ByteArrayResource imageResource = new org.springframework.core.io.ByteArrayResource(imageBytes) {
                @Override
                public String getFilename() { return "document.jpg"; }
            };

            Map<String, Object> ocrDataMap = new HashMap<>();
            ocrDataMap.put("name", app.getOcrName());
            ocrDataMap.put("dob", app.getOcrDob() != null ? app.getOcrDob().toString() : "");
            ocrDataMap.put("id_number", app.getOcrIdNumber());
            ocrDataMap.put("aadhaar_number", app.getOcrIdNumber());
            ocrDataMap.put("pan_number", app.getOcrPanNumber());
            String ocrDataJson = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(ocrDataMap);

            String aiServiceUrlLocal = "http://localhost:5001";

            org.springframework.http.HttpHeaders headers = new org.springframework.http.HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            org.springframework.util.MultiValueMap<String, Object> body = new org.springframework.util.LinkedMultiValueMap<>();
            body.add("image", imageResource);
            body.add("ocr_data", ocrDataJson);
            body.add("doc_type", docType);

            HttpEntity<org.springframework.util.MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);
            org.springframework.web.client.RestTemplate rt = new org.springframework.web.client.RestTemplate();
            ResponseEntity<String> flaskResponse = rt.exchange(
                    aiServiceUrlLocal + "/api/ai/qr-verify",
                    HttpMethod.POST,
                    requestEntity,
                    String.class
            );

            if (flaskResponse.getStatusCode().is2xxSuccessful() && flaskResponse.getBody() != null) {
                com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                com.fasterxml.jackson.databind.JsonNode root = mapper.readTree(flaskResponse.getBody());
                com.fasterxml.jackson.databind.JsonNode data = root.path("data");

                QRVerificationResult qrResult = QRVerificationResult.builder()
                        .application(app)
                        .qrDetected(data.path("qr_detected").asBoolean(false))
                        .documentType(docType)
                        .matchPercentage(data.path("match_percentage").asDouble(0))
                        .processingTimeMs(data.path("processing_time_ms").asDouble(0))
                        .qrRawData(data.has("qr_raw_data") ? data.path("qr_raw_data").asText("") : "")
                        .build();

                String statusStr = data.path("verification_status").asText("SKIPPED").toUpperCase();
                try {
                    qrResult.setVerificationStatus(com.iob.kyc.model.QRStatus.valueOf(statusStr));
                } catch (IllegalArgumentException e) {
                    qrResult.setVerificationStatus(com.iob.kyc.model.QRStatus.SKIPPED);
                }

                com.fasterxml.jackson.databind.JsonNode results = data.path("results");
                if (results.has("name")) {
                    qrResult.setOcrName(results.path("name").path("ocr").asText(""));
                    qrResult.setQrName(results.path("name").path("qr").asText(""));
                    qrResult.setNameMatch(results.path("name").path("match").asBoolean(false));
                } else {
                    qrResult.setOcrName(app.getOcrName() != null ? app.getOcrName() : "");
                }
                if (results.has("dob")) {
                    qrResult.setOcrDob(results.path("dob").path("ocr").asText(""));
                    qrResult.setQrDob(results.path("dob").path("qr").asText(""));
                    qrResult.setDobMatch(results.path("dob").path("match").asBoolean(false));
                } else {
                    qrResult.setOcrDob(app.getOcrDob() != null ? app.getOcrDob().toString() : "");
                }
                if (results.has("aadhaar_number")) {
                    qrResult.setOcrIdNumber(results.path("aadhaar_number").path("ocr").asText(""));
                    qrResult.setQrIdNumber(results.path("aadhaar_number").path("qr").asText(""));
                    qrResult.setIdNumberMatch(results.path("aadhaar_number").path("match").asBoolean(false));
                } else {
                    qrResult.setOcrIdNumber(app.getOcrIdNumber() != null ? app.getOcrIdNumber() : "");
                }
                if (results.has("pan_number")) {
                    qrResult.setOcrPanNumber(results.path("pan_number").path("ocr").asText(""));
                    qrResult.setQrPanNumber(results.path("pan_number").path("qr").asText(""));
                    qrResult.setPanNumberMatch(results.path("pan_number").path("match").asBoolean(false));
                } else {
                    qrResult.setOcrPanNumber(app.getOcrPanNumber() != null ? app.getOcrPanNumber() : "");
                }

                qrVerificationRepository.save(qrResult);

                app.setQrVerified(true);
                app.setQrVerificationStatus(qrResult.getVerificationStatus());
                app.setQrMatchPercentage(qrResult.getMatchPercentage());
                app.setQrVerifiedAt(java.time.LocalDateTime.now());

                if (qrResult.getVerificationStatus() == com.iob.kyc.model.QRStatus.FAILED) {
                    int currentRisk = app.getRiskScore();
                    int newRisk = Math.min(currentRisk + 25, 100);
                    app.setRiskScore(newRisk);
                    if (newRisk >= 60) {
                        app.setRiskLevel(KYCApplication.RiskLevel.HIGH);
                    } else if (newRisk >= 30) {
                        app.setRiskLevel(KYCApplication.RiskLevel.MEDIUM);
                    }
                } else if (qrResult.getVerificationStatus() == com.iob.kyc.model.QRStatus.SKIPPED) {
                    int currentRisk = app.getRiskScore();
                    int newRisk = Math.min(currentRisk + 10, 100);
                    app.setRiskScore(newRisk);
                    if (newRisk >= 60) {
                        app.setRiskLevel(KYCApplication.RiskLevel.HIGH);
                    } else if (newRisk >= 30) {
                        app.setRiskLevel(KYCApplication.RiskLevel.MEDIUM);
                    }
                } else if (qrResult.getVerificationStatus() == com.iob.kyc.model.QRStatus.PASSED) {
                    int currentRisk = app.getRiskScore();
                    int newRisk = Math.max(currentRisk - 15, 0);
                    app.setRiskScore(newRisk);
                    app.setRiskLevel(KYCApplication.RiskLevel.LOW);
                }

                kycApplicationRepository.save(app);

                audit(request, "QR_VERIFY", "KYC_APPLICATION", String.valueOf(id),
                        "QR verification triggered for application " + app.getApplicationRef()
                                + " — Result: " + qrResult.getVerificationStatus());

                return ResponseEntity.ok(Map.of("success", true, "data", qrResult));
            } else {
                return ResponseEntity.status(502).body(Map.of("success", false, "message", "AI service error"));
            }
        } catch (Exception e) {
            return ResponseEntity.internalServerError().body(Map.of("success", false, "message", e.getMessage()));
        }
    }

    @DeleteMapping("/delete-all-kyc")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<?> deleteAllKycData(HttpServletRequest request) {
        try {
            long kycCount = kycApplicationRepository.count();
            long qrCount = qrVerificationRepository.count();
            long fraudCount = fraudAlertRepository.count();

            qrVerificationRepository.deleteAllInBatch();
            kycApplicationRepository.deleteAllInBatch();
            fraudAlertRepository.deleteAllInBatch();

            java.io.File uploadDir = Paths.get(uploadBaseDir).toAbsolutePath().toFile();
            if (uploadDir.exists() && uploadDir.isDirectory()) {
                deleteDir(uploadDir);
            }
            Paths.get(uploadBaseDir).toAbsolutePath().toFile().mkdirs();

            auditLogService.log("ADMIN", "DELETE_ALL_KYC", "KYCApplication", null,
                    "Deleted " + kycCount + " KYC applications, " + qrCount + " QR verifications, " + fraudCount + " fraud alerts");

            return ResponseEntity.ok(Map.of(
                    "success", true,
                    "message", "All KYC data deleted successfully",
                    "deletedApplications", kycCount,
                    "deletedQrResults", qrCount,
                    "deletedFraudAlerts", fraudCount
            ));
        } catch (Exception e) {
            return ResponseEntity.internalServerError().body(Map.of("success", false, "message", "Failed to delete data: " + e.getMessage()));
        }
    }

    @DeleteMapping("/applications/{id}")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER')")
    public ResponseEntity<?> deleteKycApplication(@PathVariable Long id, HttpServletRequest request) {
        try {
            KYCApplication app = kycApplicationRepository.findById(id).orElse(null);
            if (app == null) {
                return ResponseEntity.status(404).body(Map.of("success", false, "message", "Application not found"));
            }

            String appRef = app.getApplicationRef();
            String appName = app.getOcrName();

            qrVerificationRepository.deleteAll(qrVerificationRepository.findByApplicationIdOrderByVerifiedAtDesc(id));

            String[] filePaths = { app.getSelfieFilePath(), app.getDocFilePath(), app.getAadhaarFrontPath(), app.getAadhaarBackPath(), app.getPanCardPath(), app.getPhotoFilePath() };
            for (String fp : filePaths) {
                if (fp != null && !fp.isEmpty()) {
                    try {
                        Path p = Paths.get(fp);
                        if (!Files.exists(p)) {
                            String rel = fp.startsWith("uploads/") ? fp.substring("uploads/".length()) : fp;
                            p = Paths.get(uploadBaseDir).resolve(rel).normalize();
                        }
                        if (Files.exists(p)) {
                            java.io.File f = p.toFile();
                            if (f.isFile()) f.delete();
                            java.io.File parent = f.getParentFile();
                            if (parent != null && parent.isDirectory() && parent.list() != null && parent.list().length == 0) {
                                parent.delete();
                            }
                        }
                    } catch (Exception ignored) {}
                }
            }

            kycApplicationRepository.deleteById(id);

            auditLogService.log("ADMIN", "DELETE_APPLICATION", "KYCApplication", String.valueOf(id),
                    "Deleted application " + appRef + " for " + appName);

            return ResponseEntity.ok(Map.of("success", true, "message", "Application deleted successfully", "id", id));
        } catch (Exception e) {
            return ResponseEntity.internalServerError().body(Map.of("success", false, "message", "Failed to delete: " + e.getMessage()));
        }
    }

    private void deleteDir(java.io.File dir) {
        if (dir == null || !dir.exists()) return;
        java.io.File[] files = dir.listFiles();
        if (files != null) {
            for (java.io.File f : files) {
                if (f.isDirectory()) {
                    deleteDir(f);
                } else {
                    f.delete();
                }
            }
        }
        dir.delete();
    }
}
