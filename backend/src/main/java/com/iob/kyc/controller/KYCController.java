package com.iob.kyc.controller;

import com.iob.kyc.dto.ApiResponse;
import com.iob.kyc.dto.KYCSubmitRequest;
import com.iob.kyc.model.KYCApplication;
import com.iob.kyc.model.QRVerificationResult;
import com.iob.kyc.repository.KYCApplicationRepository;
import com.iob.kyc.repository.QRVerificationRepository;
import com.iob.kyc.repository.UserRepository;
import com.iob.kyc.service.AuditLogService;
import com.iob.kyc.service.KYCService;
import com.lowagie.text.*;
import com.lowagie.text.pdf.*;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.client.RestTemplate;

import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/kyc")
public class KYCController {

    private static final org.slf4j.Logger logger = org.slf4j.LoggerFactory.getLogger(KYCController.class);

    private final KYCService kycService;
    private final UserRepository userRepository;
    private final KYCApplicationRepository kycApplicationRepository;
    private final QRVerificationRepository qrVerificationRepository;
    private final RestTemplate restTemplate;
    private final AuditLogService auditLogService;

    @Value("${file.upload-dir:./uploads}")
    private String uploadBaseDir;

    @Value("${ai-service.url:http://localhost:5001}")
    private String aiServiceUrl;

    public KYCController(KYCService kycService, UserRepository userRepository,
                         KYCApplicationRepository kycApplicationRepository,
                         QRVerificationRepository qrVerificationRepository,
                         AuditLogService auditLogService,
                         com.iob.kyc.repository.BranchRepository branchRepository) {
        this.kycService = kycService;
        this.userRepository = userRepository;
        this.kycApplicationRepository = kycApplicationRepository;
        this.qrVerificationRepository = qrVerificationRepository;
        this.restTemplate = new RestTemplate();
        this.auditLogService = auditLogService;
        this.branchRepository = branchRepository;
    }

    private final com.iob.kyc.repository.BranchRepository branchRepository;

    @GetMapping("/branches")
    public ResponseEntity<?> listBranches() {
        var branches = branchRepository.findByActiveTrueOrderByBranchName();
        return ResponseEntity.ok(ApiResponse.success("Branches retrieved", branches));
    }

    @PostMapping("/submit")
    public ResponseEntity<ApiResponse> submitKyc(@RequestBody KYCSubmitRequest request,
                                                  Authentication authentication,
                                                  HttpServletRequest httpRequest) {
        Long userId = getUserId(authentication);
        String ipAddress = getClientIp(httpRequest);
        String userAgent = httpRequest.getHeader("User-Agent");
        String device = parseDeviceFromUA(userAgent);
        KYCSubmitRequest enriched = new KYCSubmitRequest(
                request.docType(), request.ocrName(), request.ocrDob(),
                request.ocrIdNumber(), request.ocrPanNumber(),
                request.ocrAddress(), request.mobile(), request.email(),
                request.accountType(), request.gender(), request.riskScore(),
                request.faceMatchPercent(), request.livenessPassed(), ipAddress,
                request.applicationType(), request.existingAppId(), request.branch(), request.remarks()
        );

        ApiResponse response = kycService.submitKYC(userId, enriched, device);
        auditLogService.log(String.valueOf(userId), "KYC_SUBMIT", "KYCApplication",
                String.valueOf(userId), "KYC application submitted from " + device);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    private String getClientIp(HttpServletRequest request) {
        String ip = request.getHeader("X-Forwarded-For");
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getHeader("X-Real-IP");
        }
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getRemoteAddr();
        }
        if (ip != null && ip.contains(",")) {
            ip = ip.split(",")[0].trim();
        }
        return ip != null ? ip : "0.0.0.0";
    }

    private String parseDeviceFromUA(String userAgent) {
        if (userAgent == null || userAgent.isEmpty()) return "Unknown Device";
        String ua = userAgent;

        // Detect browser
        String browser = "Unknown Browser";
        if (ua.contains("Edg/")) browser = "Edge";
        else if (ua.contains("OPR/") || ua.contains("Opera")) browser = "Opera";
        else if (ua.contains("Chrome") && !ua.contains("Edg")) browser = "Chrome";
        else if (ua.contains("Firefox")) browser = "Firefox";
        else if (ua.contains("Safari") && !ua.contains("Chrome")) browser = "Safari";

        // Detect OS
        String os = "Unknown OS";
        if (ua.contains("Windows NT 10")) os = "Windows 10/11";
        else if (ua.contains("Windows NT 6.3")) os = "Windows 8.1";
        else if (ua.contains("Windows NT 6.2")) os = "Windows 8";
        else if (ua.contains("Windows NT 6.1")) os = "Windows 7";
        else if (ua.contains("Windows")) os = "Windows";
        else if (ua.contains("Mac OS X")) {
            int idx = ua.indexOf("Mac OS X ");
            if (idx >= 0) {
                int end = ua.indexOf(")", idx);
                os = "macOS " + ua.substring(idx + 9, end > idx ? end : idx + 20).replace("_", ".");
            } else {
                os = "macOS";
            }
        }
        else if (ua.contains("Android")) {
            int idx = ua.indexOf("Android ");
            if (idx >= 0) {
                int end = ua.indexOf(";", idx);
                os = "Android " + ua.substring(idx + 8, end > idx ? end : idx + 12).trim();
            } else {
                os = "Android";
            }
        }
        else if (ua.contains("iPhone") || ua.contains("iPad")) {
            int idx = ua.indexOf("OS ");
            if (idx >= 0) {
                int end = ua.indexOf(")", idx);
                os = "iOS " + ua.substring(idx + 3, end > idx ? end : idx + 8).replace("_", ".");
            } else {
                os = "iOS";
            }
        }
        else if (ua.contains("Linux")) os = "Linux";
        else if (ua.contains("CrOS")) os = "Chrome OS";

        return browser + " / " + os;
    }

    @PostMapping("/{id}/document")
    public ResponseEntity<ApiResponse> uploadDocument(@PathVariable Long id, @RequestParam("document") MultipartFile file) {
        try {
            byte[] bytes = file.getBytes();
            String base64 = "data:" + (file.getContentType() != null ? file.getContentType() : "image/jpeg") + ";base64," + java.util.Base64.getEncoder().encodeToString(bytes);
            kycApplicationRepository.findById(id).ifPresent(app -> {
                app.setDocFileBase64(base64);
                kycApplicationRepository.save(app);
            });
        } catch (Exception e) { logger.warn("[KYC] Failed to save document base64: {}", e.getMessage()); }
        ApiResponse response = kycService.uploadDocument(id, file);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping("/{id}/selfie")
    public ResponseEntity<ApiResponse> uploadSelfie(@PathVariable Long id, @RequestParam("selfie") MultipartFile file) {
        try {
            byte[] bytes = file.getBytes();
            String base64 = "data:" + (file.getContentType() != null ? file.getContentType() : "image/jpeg") + ";base64," + java.util.Base64.getEncoder().encodeToString(bytes);
            kycApplicationRepository.findById(id).ifPresent(app -> {
                app.setSelfieBase64(base64);
                kycApplicationRepository.save(app);
            });
        } catch (Exception e) {
            logger.warn("[KYC] Failed to save selfie base64: {}", e.getMessage());
        }
        ApiResponse response = kycService.uploadSelfie(id, file);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping("/{id}/photo")
    public ResponseEntity<ApiResponse> uploadPhoto(@PathVariable Long id, @RequestParam("photo") MultipartFile file) {
        try {
            byte[] bytes = file.getBytes();
            String base64 = "data:" + (file.getContentType() != null ? file.getContentType() : "image/jpeg") + ";base64," + java.util.Base64.getEncoder().encodeToString(bytes);
            kycApplicationRepository.findById(id).ifPresent(app -> {
                app.setPhotoBase64(base64);
                kycApplicationRepository.save(app);
            });
        } catch (Exception e) {
            logger.warn("[KYC] Failed to save photo base64: {}", e.getMessage());
        }
        ApiResponse response = kycService.uploadPhoto(id, file);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping("/{id}/aadhaar-front")
    public ResponseEntity<ApiResponse> uploadAadhaarFront(@PathVariable Long id, @RequestParam("file") MultipartFile file) {
        try {
            byte[] bytes = file.getBytes();
            String base64 = "data:" + (file.getContentType() != null ? file.getContentType() : "image/jpeg") + ";base64," + java.util.Base64.getEncoder().encodeToString(bytes);
            kycApplicationRepository.findById(id).ifPresent(app -> {
                app.setAadhaarFrontBase64(base64);
                kycApplicationRepository.save(app);
            });
        } catch (Exception e) { logger.warn("[KYC] Failed to save aadhaar front base64: {}", e.getMessage()); }
        return ResponseEntity.status(200).body(kycService.uploadAadhaarFront(id, file));
    }

    @PostMapping("/{id}/aadhaar-back")
    public ResponseEntity<ApiResponse> uploadAadhaarBack(@PathVariable Long id, @RequestParam("file") MultipartFile file) {
        try {
            byte[] bytes = file.getBytes();
            String base64 = "data:" + (file.getContentType() != null ? file.getContentType() : "image/jpeg") + ";base64," + java.util.Base64.getEncoder().encodeToString(bytes);
            kycApplicationRepository.findById(id).ifPresent(app -> {
                app.setAadhaarBackBase64(base64);
                kycApplicationRepository.save(app);
            });
        } catch (Exception e) { logger.warn("[KYC] Failed to save aadhaar back base64: {}", e.getMessage()); }
        return ResponseEntity.status(200).body(kycService.uploadAadhaarBack(id, file));
    }

    @PostMapping("/{id}/pan-card")
    public ResponseEntity<ApiResponse> uploadPanCard(@PathVariable Long id, @RequestParam("file") MultipartFile file) {
        try {
            byte[] bytes = file.getBytes();
            String base64 = "data:" + (file.getContentType() != null ? file.getContentType() : "image/jpeg") + ";base64," + java.util.Base64.getEncoder().encodeToString(bytes);
            kycApplicationRepository.findById(id).ifPresent(app -> {
                app.setPanCardBase64(base64);
                kycApplicationRepository.save(app);
            });
        } catch (Exception e) { logger.warn("[KYC] Failed to save pan card base64: {}", e.getMessage()); }
        return ResponseEntity.status(200).body(kycService.uploadPanCard(id, file));
    }

    @PostMapping("/{id}/challenge-video")
    public ResponseEntity<ApiResponse> uploadChallengeVideo(@PathVariable Long id,
                                                            @RequestBody Map<String, String> body) {
        try {
            String videoBase64 = body.get("videoBase64");
            String challengeResults = body.get("challengeResults");
            String challengeSequence = body.get("challengeSequence");

            kycApplicationRepository.findById(id).ifPresent(app -> {
                if (videoBase64 != null) {
                    app.setChallengeResponseVideoBase64(videoBase64);
                }
                if (challengeResults != null) {
                    app.setChallengeResults(challengeResults);
                }
                if (challengeSequence != null) {
                    app.setChallengeSequence(challengeSequence);
                }
                app.setVerificationTimestamp(LocalDateTime.now());
                kycApplicationRepository.save(app);
            });

            auditLogService.log(String.valueOf(id), "CHALLENGE_VIDEO_UPLOAD", "KYCApplication",
                    String.valueOf(id), "Challenge response video uploaded for application " + id);

            return ResponseEntity.ok(ApiResponse.success("Challenge video uploaded successfully", null));
        } catch (Exception e) {
            logger.warn("[KYC] Failed to save challenge video: {}", e.getMessage());
            return ResponseEntity.status(500).body(ApiResponse.error("Failed to save challenge video", 500));
        }
    }

    @GetMapping("/status")
    public ResponseEntity<ApiResponse> getKycStatus(Authentication authentication) {
        Long userId = getUserId(authentication);
        ApiResponse response = kycService.getKYCStatus(userId);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @GetMapping("/{id}/document")
    public ResponseEntity<byte[]> getApplicationDocument(@PathVariable Long id, Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        return kycApplicationRepository.findByIdWithUser(id)
                .filter(app -> app.getUser().getId().equals(userId))
                .map(app -> {
                    var resp = serveFileField(app.getDocFilePath());
                    if (resp.getStatusCode().is4xxClientError() && app.getDocFileBase64() != null && !app.getDocFileBase64().isEmpty()) {
                        return serveBase64(app.getDocFileBase64());
                    }
                    return resp;
                })
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}/selfie")
    public ResponseEntity<byte[]> getApplicationSelfie(@PathVariable Long id, Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        return kycApplicationRepository.findByIdWithUser(id)
                .filter(app -> app.getUser().getId().equals(userId))
                .map(app -> {
                    var resp = serveFileField(app.getSelfieFilePath());
                    if (resp.getStatusCode().is4xxClientError() && app.getSelfieBase64() != null && !app.getSelfieBase64().isEmpty()) {
                        return serveBase64(app.getSelfieBase64());
                    }
                    return resp;
                })
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}/photo")
    public ResponseEntity<byte[]> getApplicationPhoto(@PathVariable Long id, Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        return kycApplicationRepository.findByIdWithUser(id)
                .filter(app -> app.getUser().getId().equals(userId))
                .map(app -> {
                    var resp = serveFileField(app.getPhotoFilePath());
                    if (resp.getStatusCode().is4xxClientError() && app.getPhotoBase64() != null && !app.getPhotoBase64().isEmpty()) {
                        return serveBase64(app.getPhotoBase64());
                    }
                    return resp;
                })
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}/aadhaar-front")
    public ResponseEntity<byte[]> getAadhaarFront(@PathVariable Long id, Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        return kycApplicationRepository.findByIdWithUser(id)
                .filter(app -> app.getUser().getId().equals(userId))
                .map(app -> {
                    var resp = serveFileField(app.getAadhaarFrontPath());
                    if (resp.getStatusCode().is4xxClientError() && app.getAadhaarFrontBase64() != null && !app.getAadhaarFrontBase64().isEmpty()) {
                        return serveBase64(app.getAadhaarFrontBase64());
                    }
                    return resp;
                })
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}/aadhaar-back")
    public ResponseEntity<byte[]> getAadhaarBack(@PathVariable Long id, Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        return kycApplicationRepository.findByIdWithUser(id)
                .filter(app -> app.getUser().getId().equals(userId))
                .map(app -> {
                    var resp = serveFileField(app.getAadhaarBackPath());
                    if (resp.getStatusCode().is4xxClientError() && app.getAadhaarBackBase64() != null && !app.getAadhaarBackBase64().isEmpty()) {
                        return serveBase64(app.getAadhaarBackBase64());
                    }
                    return resp;
                })
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}/pan-card")
    public ResponseEntity<byte[]> getPanCard(@PathVariable Long id, Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        return kycApplicationRepository.findByIdWithUser(id)
                .filter(app -> app.getUser().getId().equals(userId))
                .map(app -> {
                    var resp = serveFileField(app.getPanCardPath());
                    if (resp.getStatusCode().is4xxClientError() && app.getPanCardBase64() != null && !app.getPanCardBase64().isEmpty()) {
                        return serveBase64(app.getPanCardBase64());
                    }
                    return resp;
                })
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/profile-photo")
    public ResponseEntity<?> getProfilePhoto(Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        List<KYCApplication> apps = kycApplicationRepository.findByUserIdOrderByIdDesc(userId);
        if (apps.isEmpty()) return ResponseEntity.notFound().build();
        // Find the first application with an actual profile photo (prefer APPROVED)
        KYCApplication best = null;
        for (KYCApplication app : apps) {
            if (app.getStatus() == KYCApplication.Status.APPROVED && app.getPhotoFilePath() != null && !app.getPhotoFilePath().isEmpty()) {
                best = app;
                break;
            }
        }
        if (best == null) {
            for (KYCApplication app : apps) {
                if (app.getPhotoFilePath() != null && !app.getPhotoFilePath().isEmpty()) {
                    best = app;
                    break;
                }
            }
        }
        if (best == null) best = apps.get(0);
        return serveFileField(best.getPhotoFilePath());
    }

    @GetMapping("/approved")
    public ResponseEntity<ApiResponse> getLatestApproved(Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        List<KYCApplication> apps = kycApplicationRepository.findByUserIdOrderByIdDesc(userId);
        for (KYCApplication app : apps) {
            if (app.getStatus() == KYCApplication.Status.APPROVED) {
                return ResponseEntity.ok(ApiResponse.success("Approved application found", app));
            }
        }
        return ResponseEntity.ok(ApiResponse.error("No approved application found", 404));
    }

    @GetMapping("/{id}/details")
    public ResponseEntity<ApiResponse> getApplicationDetails(@PathVariable Long id, Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        return kycApplicationRepository.findByIdWithUser(id)
                .filter(app -> app.getUser().getId().equals(userId))
                .map(app -> ResponseEntity.ok(ApiResponse.success("Application details", app)))
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}/pdf")
    public ResponseEntity<byte[]> downloadKycPdf(@PathVariable Long id, Authentication authentication) {
        Long userId = (authentication != null && authentication.getName() != null)
                ? userRepository.findByEmail(authentication.getName()).map(com.iob.kyc.model.User::getId).orElse(null)
                : null;
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();

        KYCApplication app = kycApplicationRepository.findByIdWithUser(id)
                .filter(a -> a.getUser().getId().equals(userId))
                .orElse(null);
        if (app == null) return ResponseEntity.notFound().build();

        try {
            byte[] pdfBytes = generateKycPdf(app);
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=KYC_" + app.getApplicationRef() + ".pdf")
                    .contentType(MediaType.APPLICATION_PDF)
                    .body(pdfBytes);
        } catch (Exception e) {
            return ResponseEntity.internalServerError().build();
        }
    }

    @GetMapping("/{id}/compare/{otherId}")
    public ResponseEntity<Map<String, Object>> compareApplications(
            @PathVariable Long id, @PathVariable Long otherId, Authentication authentication) {
        Long userId = (authentication != null && authentication.getName() != null)
                ? userRepository.findByEmail(authentication.getName()).map(com.iob.kyc.model.User::getId).orElse(null)
                : null;
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();

        KYCApplication oldApp = kycApplicationRepository.findByIdWithUser(id).orElse(null);
        KYCApplication newApp = kycApplicationRepository.findByIdWithUser(otherId).orElse(null);
        if (oldApp == null || newApp == null) return ResponseEntity.notFound().build();

        boolean nameChanged = !java.util.Objects.equals(oldApp.getOcrName(), newApp.getOcrName());
        boolean addressChanged = !java.util.Objects.equals(oldApp.getOcrAddress(), newApp.getOcrAddress());
        boolean idChanged = !java.util.Objects.equals(oldApp.getOcrIdNumber(), newApp.getOcrIdNumber());
        boolean panChanged = !java.util.Objects.equals(oldApp.getOcrPanNumber(), newApp.getOcrPanNumber());
        boolean dobChanged = !java.util.Objects.equals(oldApp.getOcrDob(), newApp.getOcrDob());

        return ResponseEntity.ok(Map.of(
                "old", oldApp,
                "new", newApp,
                "changes", Map.of(
                        "name", nameChanged,
                        "address", addressChanged,
                        "idNumber", idChanged,
                        "panNumber", panChanged,
                        "dob", dobChanged,
                        "hasChanges", nameChanged || addressChanged || idChanged || panChanged || dobChanged
                )
        ));
    }

    private byte[] generateKycPdf(KYCApplication app) throws Exception {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        Document document = new Document(PageSize.A4, 36, 36, 36, 36);
        PdfWriter.getInstance(document, baos);
        document.open();

        Font titleFont = FontFactory.getFont(FontFactory.HELVETICA_BOLD, 18, new java.awt.Color(0, 71, 171));
        Font headerFont = FontFactory.getFont(FontFactory.HELVETICA_BOLD, 12, java.awt.Color.DARK_GRAY);
        Font bodyFont = FontFactory.getFont(FontFactory.HELVETICA, 11, java.awt.Color.BLACK);
        Font labelFont = FontFactory.getFont(FontFactory.HELVETICA_BOLD, 11, java.awt.Color.GRAY);
        DateTimeFormatter fmt = DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm a");

        document.add(new Paragraph("Indian Overseas Bank - KYC Details", titleFont));
        document.add(new Paragraph("Application Reference: " + app.getApplicationRef(), bodyFont));
        document.add(Chunk.NEWLINE);

        Paragraph section1 = new Paragraph("Personal Information", headerFont);
        document.add(section1);
        document.add(Chunk.NEWLINE);

        PdfPTable table = new PdfPTable(2);
        table.setWidthPercentage(100);
        table.setWidths(new float[]{35, 65});
        table.setSpacingBefore(5);
        table.setSpacingAfter(5);

        addRow(table, "Full Name", app.getOcrName(), labelFont, bodyFont);
        addRow(table, "Date of Birth", app.getOcrDob() != null ? app.getOcrDob().format(fmt) : "--", labelFont, bodyFont);
        addRow(table, "Aadhaar Number", app.getOcrIdNumber(), labelFont, bodyFont);
        addRow(table, "PAN Number", app.getOcrPanNumber(), labelFont, bodyFont);
        addRow(table, "Address", app.getOcrAddress(), labelFont, bodyFont);
        addRow(table, "Application Type", app.getApplicationType().name(), labelFont, bodyFont);
        addRow(table, "Status", app.getStatus().name(), labelFont, bodyFont);
        addRow(table, "Submitted", app.getSubmittedAt() != null ? app.getSubmittedAt().format(fmt) : "--", labelFont, bodyFont);
        addRow(table, "Reviewed", app.getReviewedAt() != null ? app.getReviewedAt().format(fmt) : "--", labelFont, bodyFont);
        addRow(table, "Face Match", app.getFaceMatchPercentage() != null ? app.getFaceMatchPercentage() + "%" : "--", labelFont, bodyFont);
        addRow(table, "Liveness", app.isLivenessPassed() ? "Passed" : "Failed", labelFont, bodyFont);
        addRow(table, "Risk Level", app.getRiskLevel() != null ? app.getRiskLevel().name() : "LOW", labelFont, bodyFont);
        addRow(table, "QR Verification", app.getQrVerificationStatus() != null ? app.getQrVerificationStatus().name() : "Not Performed", labelFont, bodyFont);
        if (app.getQrMatchPercentage() != null) {
            addRow(table, "QR Match %", app.getQrMatchPercentage() + "%", labelFont, bodyFont);
        }
        document.add(table);

        document.add(Chunk.NEWLINE);
        Paragraph footer = new Paragraph("This document is system-generated. For official use only.", FontFactory.getFont(FontFactory.HELVETICA, 9, java.awt.Color.GRAY));
        document.add(footer);

        document.close();
        return baos.toByteArray();
    }

    private void addRow(PdfPTable table, String label, String value, Font labelFont, Font bodyFont) {
        PdfPCell labelCell = new PdfPCell(new Phrase(label, labelFont));
        labelCell.setPadding(8);
        labelCell.setBorderColor(java.awt.Color.LIGHT_GRAY);
        table.addCell(labelCell);
        PdfPCell valueCell = new PdfPCell(new Phrase(value != null ? value : "--", bodyFont));
        valueCell.setPadding(8);
        valueCell.setBorderColor(java.awt.Color.LIGHT_GRAY);
        table.addCell(valueCell);
    }

    private ResponseEntity<byte[]> serveFileField(String filePath) {
        if (filePath == null || filePath.isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        try {
            Path path = Paths.get(filePath);
            if (!Files.exists(path)) {
                String relativePath = filePath;
                if (relativePath.startsWith("uploads/") || relativePath.startsWith("uploads\\")) {
                    relativePath = relativePath.substring("uploads/".length());
                }
                Path altPath = Paths.get(uploadBaseDir).toAbsolutePath().normalize().resolve(relativePath).normalize();
                if (Files.exists(altPath)) {
                    path = altPath;
                } else {
                    logger.warn("[KYC-Serve] File not found: original='{}', alt='{}'", filePath, altPath);
                    return ResponseEntity.notFound().build();
                }
            }
            byte[] imageBytes = Files.readAllBytes(path);
            String contentType = Files.probeContentType(path);
            if (contentType == null) contentType = MediaType.APPLICATION_OCTET_STREAM_VALUE;
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_TYPE, contentType)
                    .body(imageBytes);
        } catch (Exception e) {
            logger.error("[KYC-Serve] Error serving file: {}", e.getMessage(), e);
            return ResponseEntity.internalServerError().build();
        }
    }

    private ResponseEntity<byte[]> serveBase64(String base64Data) {
        try {
            String data = base64Data;
            String contentType = "image/jpeg";
            if (data.startsWith("data:")) {
                int commaIdx = data.indexOf(',');
                if (commaIdx > 0) {
                    contentType = data.substring(5, commaIdx);
                    data = data.substring(commaIdx + 1);
                }
            }
            byte[] bytes = java.util.Base64.getDecoder().decode(data);
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_TYPE, contentType)
                    .body(bytes);
        } catch (Exception e) {
            return ResponseEntity.notFound().build();
        }
    }

    // ============================================================
    // QR CODE VERIFICATION ENDPOINTS
    // ============================================================

    @PostMapping("/{id}/qr-verify")
    public ResponseEntity<ApiResponse> triggerQrVerification(@PathVariable Long id, Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();

        KYCApplication app = kycApplicationRepository.findByIdWithUser(id).orElse(null);
        if (app == null) return ResponseEntity.notFound().build();

        if (!app.getUser().getId().equals(userId)) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        }

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
            return ResponseEntity.badRequest().body(ApiResponse.error("No document image uploaded for QR verification", 400));
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
                    return ResponseEntity.badRequest().body(ApiResponse.error("Document image file not found", 400));
                }
            }

            byte[] imageBytes = Files.readAllBytes(path);

            org.springframework.core.io.ByteArrayResource imageResource = new org.springframework.core.io.ByteArrayResource(imageBytes) {
                @Override
                public String getFilename() {
                    return "document.jpg";
                }
            };

            java.util.Map<String, Object> ocrDataMap = new java.util.HashMap<>();
            ocrDataMap.put("name", app.getOcrName());
            ocrDataMap.put("dob", app.getOcrDob() != null ? app.getOcrDob().toString() : "");
            ocrDataMap.put("id_number", app.getOcrIdNumber());
            ocrDataMap.put("aadhaar_number", app.getOcrIdNumber());
            ocrDataMap.put("pan_number", app.getOcrPanNumber());
            String ocrDataJson = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(ocrDataMap);

            org.springframework.http.HttpHeaders headers = new org.springframework.http.HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            org.springframework.util.MultiValueMap<String, Object> body = new org.springframework.util.LinkedMultiValueMap<>();
            body.add("image", imageResource);
            body.add("ocr_data", ocrDataJson);
            body.add("doc_type", docType);

            HttpEntity<org.springframework.util.MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);
            ResponseEntity<String> flaskResponse = restTemplate.exchange(
                    aiServiceUrl + "/api/ai/qr-verify",
                    HttpMethod.POST,
                    requestEntity,
                    String.class
            );

            if (flaskResponse.getStatusCode().is2xxSuccessful() && flaskResponse.getBody() != null) {
                com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                com.fasterxml.jackson.databind.JsonNode root = mapper.readTree(flaskResponse.getBody());

                boolean success = root.path("success").asBoolean(false);
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

                auditLogService.log(String.valueOf(userId), "QR_VERIFICATION", "KYCApplication",
                        String.valueOf(id), "QR verification completed for application " + id);

                return ResponseEntity.ok(ApiResponse.success("QR verification completed", qrResult));
            } else {
                return ResponseEntity.status(502).body(ApiResponse.error("AI service returned error", 502));
            }
        } catch (Exception e) {
            logger.error("[QRVerify] Error for application {}: {}", id, e.getMessage(), e);
            return ResponseEntity.internalServerError().body(ApiResponse.error("QR verification failed: " + e.getMessage(), 500));
        }
    }

    @GetMapping("/{id}/qr-verify")
    public ResponseEntity<ApiResponse> getQrVerificationResult(@PathVariable Long id, Authentication authentication) {
        Long userId = getUserId(authentication);
        if (userId == null) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();

        KYCApplication app = kycApplicationRepository.findByIdWithUser(id).orElse(null);
        if (app == null) return ResponseEntity.notFound().build();

        if (!app.getUser().getId().equals(userId)) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        }

        java.util.Optional<QRVerificationResult> qrResult = qrVerificationRepository.findFirstByApplicationIdOrderByVerifiedAtDesc(id);
        if (qrResult.isPresent()) {
            QRVerificationResult qr = qrResult.get();
            Map<String, Object> result = new java.util.HashMap<>();
            result.put("qrDetected", qr.isQrDetected());
            result.put("verificationStatus", qr.getVerificationStatus() != null ? qr.getVerificationStatus().name() : "SKIPPED");
            result.put("matchPercentage", qr.getMatchPercentage());
            result.put("documentType", qr.getDocumentType());
            result.put("verifiedAt", qr.getVerifiedAt());
            result.put("results", qr.getResults());
            return ResponseEntity.ok(ApiResponse.success("QR verification result", result));
        } else {
            return ResponseEntity.ok(ApiResponse.success("No QR verification performed", null));
        }
    }

    private Long getUserId(Authentication authentication) {
        if (authentication != null && authentication.getName() != null) {
            return userRepository.findByEmail(authentication.getName())
                    .map(com.iob.kyc.model.User::getId)
                    .orElse(null);
        }
        return null;
    }
}
