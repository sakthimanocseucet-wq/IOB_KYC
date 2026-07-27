package com.iob.kyc.service;

import com.iob.kyc.dto.ApiResponse;
import com.iob.kyc.dto.KYCSubmitRequest;
import com.iob.kyc.model.KYCApplication;
import com.iob.kyc.model.User;
import com.iob.kyc.repository.KYCApplicationRepository;
import com.iob.kyc.repository.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Service
public class KYCService {

    private static final Logger logger = LoggerFactory.getLogger(KYCService.class);

    @Value("${file.upload-dir:./uploads}")
    private String uploadBaseDir;

    private final KYCApplicationRepository kycApplicationRepository;
    private final UserRepository userRepository;

    public KYCService(KYCApplicationRepository kycApplicationRepository, UserRepository userRepository) {
        this.kycApplicationRepository = kycApplicationRepository;
        this.userRepository = userRepository;
    }

    @Transactional
    public ApiResponse submitKYC(Long userId, KYCSubmitRequest request, String device) {
        // PII-safe logging: only log non-sensitive metadata
        logger.info("[KYCService] submitKYC userId={} docType={}", userId, request.docType());

        User user = userRepository.findById(userId).orElse(null);

        if (user == null) {
            return ApiResponse.error("User not found", 404);
        }

        KYCApplication.ApplicationType appType = KYCApplication.ApplicationType.NORMAL;
        if (request.applicationType() != null && request.applicationType().equalsIgnoreCase("RE_KYC")) {
            appType = KYCApplication.ApplicationType.RE_KYC;
        }

        // Prevent duplicate PENDING applications per user — update existing instead of creating new
        KYCApplication application = null;
        if (appType == KYCApplication.ApplicationType.NORMAL) {
            List<KYCApplication> existingApps = kycApplicationRepository.findByUserIdOrderByIdDesc(userId);
            for (KYCApplication existing : existingApps) {
                if (existing.getStatus() == KYCApplication.Status.PENDING && existing.getApplicationType() == appType) {
                    application = existing;
                    logger.info("[KYCService] Updating existing PENDING application id={} for user={}", application.getId(), userId);
                    break;
                }
            }
        }

        if (application == null) {
            // No existing PENDING app — create new
            application = KYCApplication.builder()
                    .user(user)
                    .docType(KYCApplication.DocType.valueOf(request.docType().toUpperCase()))
                    .applicationType(appType)
                    .ocrName(request.ocrName())
                    .ocrIdNumber(request.ocrIdNumber())
                    .ocrPanNumber(request.ocrPanNumber())
                    .ocrAddress(request.ocrAddress())
                    .mobile(request.mobile())
                    .email(request.email())
                    .gender(request.gender())
                    .ipAddress(request.ipAddress())
                    .device(device != null ? device : "Unknown Device")
                    .location("India")
                    .reKycStatus(appType == KYCApplication.ApplicationType.RE_KYC ? "PENDING" : null)
                    .status(KYCApplication.Status.PENDING)
                    .submittedAt(LocalDateTime.now())
                    .build();
        } else {
            // Update existing PENDING application with latest data
            application.setDocType(KYCApplication.DocType.valueOf(request.docType().toUpperCase()));
            application.setOcrName(request.ocrName());
            application.setOcrIdNumber(request.ocrIdNumber());
            application.setOcrPanNumber(request.ocrPanNumber());
            application.setOcrAddress(request.ocrAddress());
            application.setMobile(request.mobile());
            application.setEmail(request.email());
            if (request.gender() != null && !request.gender().isEmpty()) {
                application.setGender(request.gender());
            }
            application.setIpAddress(request.ipAddress());
            application.setDevice(device != null ? device : "Unknown Device");
            application.setSubmittedAt(LocalDateTime.now());
        }

        if (request.branch() != null && !request.branch().isEmpty()) {
            application.setBranchId(request.branch());
        }
        if (request.accountType() != null && !request.accountType().isEmpty()) {
            try {
                application.setAccountType(KYCApplication.AccountType.valueOf(request.accountType().toUpperCase()));
            } catch (IllegalArgumentException ignored) {}
        }

        if (request.ocrDob() != null && !request.ocrDob().isEmpty()) {
            try {
                if (request.ocrDob().contains("T")) {
                    application.setOcrDob(LocalDateTime.parse(request.ocrDob()));
                } else {
                    application.setOcrDob(LocalDateTime.parse(request.ocrDob() + "T00:00:00"));
                }
            } catch (Exception ignored) {}
        }

        if (request.faceMatchPercent() != null) {
            application.setFaceMatchPercentage(BigDecimal.valueOf(request.faceMatchPercent()));
        }
        if (request.gender() != null && !request.gender().isEmpty()) {
            application.setGender(request.gender());
        }
        if (request.riskScore() != null) {
            application.setRiskScore(request.riskScore());
            if (request.riskScore() >= 60) {
                application.setRiskLevel(KYCApplication.RiskLevel.HIGH);
            } else if (request.riskScore() >= 30) {
                application.setRiskLevel(KYCApplication.RiskLevel.MEDIUM);
            } else {
                application.setRiskLevel(KYCApplication.RiskLevel.LOW);
            }
        }

        // Prefer explicit liveness flag from frontend/AI pipeline.
        // Backward compatibility: if missing, fall back to old behavior.
        if (request.livenessPassed() != null) {
            application.setLivenessPassed(request.livenessPassed());
        } else {
            // Old behavior (kept for backward compatibility): infer from faceMatchPercent.
            application.setLivenessPassed(request.faceMatchPercent() != null && request.faceMatchPercent() > 0);
        }

        kycApplicationRepository.save(application);

        // Check for duplicate mobile number across applications
        boolean duplicateMobile = false;
        int mobileUsageCount = 0;
        if (request.mobile() != null && !request.mobile().isEmpty()) {
            mobileUsageCount = (int) kycApplicationRepository.countByMobile(request.mobile());
            if (mobileUsageCount > 1) {
                duplicateMobile = true;
                logger.warn("[KYCService] Duplicate mobile detected: mobile={} count={}", request.mobile(), mobileUsageCount);
            }
        }

        if (appType == KYCApplication.ApplicationType.RE_KYC && request.existingAppId() != null) {
            KYCApplication currentApp = application;
            kycApplicationRepository.findById(request.existingAppId()).ifPresent(oldApp -> {
                // Mark old app as re-KYC initiated
                oldApp.setReKycStatus("INITIATED");
                kycApplicationRepository.save(oldApp);

                boolean updated = false;
                // Copy file paths
                if (currentApp.getAadhaarFrontPath() == null && oldApp.getAadhaarFrontPath() != null) {
                    currentApp.setAadhaarFrontPath(oldApp.getAadhaarFrontPath()); updated = true;
                }
                if (currentApp.getAadhaarBackPath() == null && oldApp.getAadhaarBackPath() != null) {
                    currentApp.setAadhaarBackPath(oldApp.getAadhaarBackPath()); updated = true;
                }
                if (currentApp.getPanCardPath() == null && oldApp.getPanCardPath() != null) {
                    currentApp.setPanCardPath(oldApp.getPanCardPath()); updated = true;
                }
                if (currentApp.getPhotoFilePath() == null && oldApp.getPhotoFilePath() != null) {
                    currentApp.setPhotoFilePath(oldApp.getPhotoFilePath()); updated = true;
                }
                if (currentApp.getDocFilePath() == null && oldApp.getDocFilePath() != null) {
                    currentApp.setDocFilePath(oldApp.getDocFilePath()); updated = true;
                }
                if (currentApp.getSelfieFilePath() == null && oldApp.getSelfieFilePath() != null) {
                    currentApp.setSelfieFilePath(oldApp.getSelfieFilePath()); updated = true;
                }
                // Copy base64 data (images stored in DB)
                if (currentApp.getAadhaarFrontBase64() == null && oldApp.getAadhaarFrontBase64() != null) {
                    currentApp.setAadhaarFrontBase64(oldApp.getAadhaarFrontBase64()); updated = true;
                }
                if (currentApp.getAadhaarBackBase64() == null && oldApp.getAadhaarBackBase64() != null) {
                    currentApp.setAadhaarBackBase64(oldApp.getAadhaarBackBase64()); updated = true;
                }
                if (currentApp.getPanCardBase64() == null && oldApp.getPanCardBase64() != null) {
                    currentApp.setPanCardBase64(oldApp.getPanCardBase64()); updated = true;
                }
                if (currentApp.getPhotoBase64() == null && oldApp.getPhotoBase64() != null) {
                    currentApp.setPhotoBase64(oldApp.getPhotoBase64()); updated = true;
                }
                if (currentApp.getDocFileBase64() == null && oldApp.getDocFileBase64() != null) {
                    currentApp.setDocFileBase64(oldApp.getDocFileBase64()); updated = true;
                }
                if (currentApp.getSelfieBase64() == null && oldApp.getSelfieBase64() != null) {
                    currentApp.setSelfieBase64(oldApp.getSelfieBase64()); updated = true;
                }
                if (updated) {
                    kycApplicationRepository.save(currentApp);
                }
            });
        }

        Map<String, Object> responseData = new java.util.HashMap<>();
        responseData.put("applicationId", application.getId());
        responseData.put("applicationRef", application.getApplicationRef());
        if (duplicateMobile) {
            responseData.put("duplicateMobile", true);
            responseData.put("mobileUsageCount", mobileUsageCount);
        }

        return ApiResponse.success("KYC application submitted successfully", responseData);
    }

    @Transactional
    public ApiResponse uploadDocument(Long applicationId, MultipartFile file) {
        KYCApplication application = kycApplicationRepository.findById(applicationId).orElse(null);
        if (application == null) {
            return ApiResponse.error("KYC application not found", 404);
        }
        if (file.isEmpty()) {
            return ApiResponse.error("File is empty", 400);
        }
        try {
            Path basePath = Paths.get(uploadBaseDir).toAbsolutePath().normalize();
            Path uploadPath = basePath.resolve("documents").resolve(String.valueOf(applicationId));
            Files.createDirectories(uploadPath);
            String safeFileName = sanitizeFilename(file.getOriginalFilename());
            String fileName = System.currentTimeMillis() + "_" + safeFileName;
            Path filePath = uploadPath.resolve(fileName).normalize();
            Files.write(filePath, file.getBytes());
            String storedPath = "uploads/documents/" + applicationId + "/" + fileName;
            application.setDocFilePath(storedPath);
            kycApplicationRepository.save(application);
            return ApiResponse.success("Document uploaded successfully", Map.of("filePath", storedPath));
        } catch (IOException e) {
            return ApiResponse.error("Failed to upload document: " + e.getMessage(), 500);
        }
    }

    @Transactional
    public ApiResponse uploadSelfie(Long applicationId, MultipartFile file) {
        KYCApplication application = kycApplicationRepository.findById(applicationId).orElse(null);
        if (application == null) {
            return ApiResponse.error("KYC application not found", 404);
        }
        if (file.isEmpty()) {
            return ApiResponse.error("File is empty", 400);
        }
        try {
            Path basePath = Paths.get(uploadBaseDir).toAbsolutePath().normalize();
            Path uploadPath = basePath.resolve("selfies").resolve(String.valueOf(applicationId));
            Files.createDirectories(uploadPath);
            String safeFileName = sanitizeFilename(file.getOriginalFilename());
            String fileName = System.currentTimeMillis() + "_" + safeFileName;
            Path filePath = uploadPath.resolve(fileName).normalize();
            Files.write(filePath, file.getBytes());
            String storedPath = "uploads/selfies/" + applicationId + "/" + fileName;
            application.setSelfieFilePath(storedPath);
            kycApplicationRepository.save(application);
            return ApiResponse.success("Selfie uploaded successfully", Map.of("filePath", storedPath));
        } catch (IOException e) {
            return ApiResponse.error("Failed to upload selfie: " + e.getMessage(), 500);
        }
    }

    @Transactional
    public ApiResponse uploadPhoto(Long applicationId, MultipartFile file) {
        KYCApplication application = kycApplicationRepository.findById(applicationId).orElse(null);
        if (application == null) {
            return ApiResponse.error("KYC application not found", 404);
        }
        if (file.isEmpty()) {
            return ApiResponse.error("File is empty", 400);
        }
        try {
            Path basePath = Paths.get(uploadBaseDir).toAbsolutePath().normalize();
            Path uploadPath = basePath.resolve("photos").resolve(String.valueOf(applicationId));
            Files.createDirectories(uploadPath);
            String safeFileName = sanitizeFilename(file.getOriginalFilename());
            String fileName = System.currentTimeMillis() + "_" + safeFileName;
            Path filePath = uploadPath.resolve(fileName).normalize();
            Files.write(filePath, file.getBytes());
            String storedPath = "uploads/photos/" + applicationId + "/" + fileName;
            application.setPhotoFilePath(storedPath);
            kycApplicationRepository.save(application);
            return ApiResponse.success("Photo uploaded successfully", Map.of("filePath", storedPath));
        } catch (IOException e) {
            return ApiResponse.error("Failed to upload photo: " + e.getMessage(), 500);
        }
    }

    @Transactional
    public ApiResponse uploadAadhaarFront(Long applicationId, MultipartFile file) {
        return uploadDocumentToField(applicationId, file, "aadhaar-front", (app, path) -> app.setAadhaarFrontPath(path));
    }

    @Transactional
    public ApiResponse uploadAadhaarBack(Long applicationId, MultipartFile file) {
        return uploadDocumentToField(applicationId, file, "aadhaar-back", (app, path) -> app.setAadhaarBackPath(path));
    }

    @Transactional
    public ApiResponse uploadPanCard(Long applicationId, MultipartFile file) {
        return uploadDocumentToField(applicationId, file, "pan-card", (app, path) -> app.setPanCardPath(path));
    }

    private ApiResponse uploadDocumentToField(Long applicationId, MultipartFile file, String subDir,
                                                java.util.function.BiConsumer<KYCApplication, String> setter) {
        KYCApplication application = kycApplicationRepository.findById(applicationId).orElse(null);
        if (application == null) {
            return ApiResponse.error("KYC application not found", 404);
        }
        if (file.isEmpty()) {
            return ApiResponse.error("File is empty", 400);
        }
        try {
            Path basePath = Paths.get(uploadBaseDir).toAbsolutePath().normalize();
            Path uploadPath = basePath.resolve(subDir).resolve(String.valueOf(applicationId));
            Files.createDirectories(uploadPath);
            String safeFileName = sanitizeFilename(file.getOriginalFilename());
            String fileName = System.currentTimeMillis() + "_" + safeFileName;
            Path filePath = uploadPath.resolve(fileName).normalize();
            Files.write(filePath, file.getBytes());
            String storedPath = "uploads/" + subDir + "/" + applicationId + "/" + fileName;
            setter.accept(application, storedPath);
            kycApplicationRepository.save(application);
            return ApiResponse.success("File uploaded successfully", Map.of("filePath", storedPath));
        } catch (IOException e) {
            return ApiResponse.error("Failed to upload file: " + e.getMessage(), 500);
        }
    }

    @Transactional(readOnly = true)
    public ApiResponse getKYCStatus(Long userId) {
        List<KYCApplication> applications = kycApplicationRepository.findByUserIdOrderByIdDesc(userId);
        if (applications.isEmpty()) {
            return ApiResponse.success("No KYC applications found", List.of());
        }
        for (KYCApplication app : applications) {
            if (app.getStatus() == KYCApplication.Status.APPROVED) {
                if (app.getAccountNumber() == null || app.getAccountNumber().isEmpty()) {
                    app.setAccountNumber("IOB" + String.format("%04d", app.getId()) + String.format("%06d", System.currentTimeMillis() % 1000000));
                }
                if (app.getIfscCode() == null || app.getIfscCode().isEmpty()) {
                    app.setIfscCode("IOBA000" + String.format("%04d", app.getId()));
                }
                if (app.getBranchId() == null || app.getBranchId().isEmpty()) {
                    app.setBranchId("BRANCH" + String.format("%03d", app.getId()));
                }
            }
        }
        return ApiResponse.success("KYC applications retrieved", applications);
    }

    private String sanitizeFilename(String filename) {
        if (filename == null || filename.isEmpty()) {
            return "upload";
        }
        // Remove path separators and null bytes to prevent path traversal
        String safe = filename.replaceAll("[\\\\/:*?\"<>|\\x00]", "_");
        // Remove leading dots to prevent hidden files
        safe = safe.replaceAll("^\\.+", "");
        // Limit length
        if (safe.length() > 100) {
            safe = safe.substring(safe.length() - 100);
        }
        return safe.isEmpty() ? "upload" : safe;
    }
}
