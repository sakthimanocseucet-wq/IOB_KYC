package com.iob.kyc.service;

import com.iob.kyc.model.Branch;
import com.iob.kyc.model.KYCApplication;
import com.iob.kyc.model.QRVerificationResult;
import com.iob.kyc.repository.BranchRepository;
import com.iob.kyc.repository.KYCApplicationRepository;
import com.iob.kyc.repository.QRVerificationRepository;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.stream.Collectors;

@Service
public class AccountDetailsService {

    private final KYCApplicationRepository kycApplicationRepository;
    private final BranchRepository branchRepository;
    private final QRVerificationRepository qrVerificationRepository;

    public AccountDetailsService(KYCApplicationRepository kycApplicationRepository,
                                  BranchRepository branchRepository,
                                  QRVerificationRepository qrVerificationRepository) {
        this.kycApplicationRepository = kycApplicationRepository;
        this.branchRepository = branchRepository;
        this.qrVerificationRepository = qrVerificationRepository;
    }

    public List<Map<String, Object>> searchAccounts(String query, String role, String branchId, String employeeId) {
        List<KYCApplication> allApps = kycApplicationRepository.findAll();

        // RBAC filtering
        if ("MANAGER".equals(role) && branchId != null && !branchId.isEmpty()) {
            allApps = allApps.stream()
                    .filter(app -> branchId.equals(app.getBranchId()))
                    .collect(Collectors.toList());
        } else if ("OFFICER".equals(role) && employeeId != null && !employeeId.isEmpty()) {
            allApps = allApps.stream()
                    .filter(app -> employeeId.equals(app.getAssignedEmployeeId()))
                    .collect(Collectors.toList());
        }

        // Search filtering
        if (query != null && !query.trim().isEmpty()) {
            String q = query.trim().toLowerCase();
            allApps = allApps.stream()
                    .filter(app -> matchesQuery(app, q))
                    .collect(Collectors.toList());
        }

        return allApps.stream()
                .map(this::toSearchResult)
                .collect(Collectors.toList());
    }

    private boolean matchesQuery(KYCApplication app, String q) {
        if (app.getAccountNumber() != null && app.getAccountNumber().toLowerCase().contains(q)) return true;
        if (app.getCustomerId() != null && app.getCustomerId().toLowerCase().contains(q)) return true;
        if (app.getApplicationRef() != null && app.getApplicationRef().toLowerCase().contains(q)) return true;
        if (app.getOcrName() != null && app.getOcrName().toLowerCase().contains(q)) return true;
        if (app.getMobile() != null && app.getMobile().contains(q)) return true;
        if (app.getOcrIdNumber() != null && app.getOcrIdNumber().contains(q)) return true;
        if (app.getOcrPanNumber() != null && app.getOcrPanNumber().toLowerCase().contains(q)) return true;
        if (app.getBranchId() != null && app.getBranchId().toLowerCase().contains(q)) return true;
        if (app.getIfscCode() != null && app.getIfscCode().toLowerCase().contains(q)) return true;
        if (app.getEmail() != null && app.getEmail().toLowerCase().contains(q)) return true;
        return false;
    }

    private Map<String, Object> toSearchResult(KYCApplication app) {
        Map<String, Object> result = new HashMap<>();
        result.put("id", app.getId());
        result.put("applicationRef", app.getApplicationRef());
        result.put("accountNumber", app.getAccountNumber() != null ? app.getAccountNumber() : "");
        result.put("customerId", app.getCustomerId() != null ? app.getCustomerId() : "");
        result.put("ocrName", app.getOcrName() != null ? app.getOcrName() : "");
        result.put("mobile", app.getMobile() != null ? app.getMobile() : "");
        result.put("email", app.getEmail() != null ? app.getEmail() : "");
        result.put("status", app.getStatus() != null ? app.getStatus().name() : "");
        result.put("riskLevel", app.getRiskLevel() != null ? app.getRiskLevel().name() : "LOW");
        result.put("riskScore", app.getRiskScore());
        result.put("branchId", app.getBranchId() != null ? app.getBranchId() : "");
        result.put("docType", app.getDocType() != null ? app.getDocType().name() : "");
        result.put("createdAt", app.getCreatedAt());
        result.put("submittedAt", app.getSubmittedAt());
        result.put("reviewedAt", app.getReviewedAt());
        return result;
    }

    public Map<String, Object> getAccountDetails(Long applicationId, String role, String branchId, String employeeId) {
        KYCApplication app = kycApplicationRepository.findByIdWithUser(applicationId).orElse(null);
        if (app == null) return null;

        // RBAC check
        if ("MANAGER".equals(role) && branchId != null && !branchId.isEmpty()) {
            if (!branchId.equals(app.getBranchId())) return null;
        } else if ("OFFICER".equals(role) && employeeId != null && !employeeId.isEmpty()) {
            if (!employeeId.equals(app.getAssignedEmployeeId())) return null;
        }

        Map<String, Object> details = new HashMap<>();

        // Basic info
        details.put("id", app.getId());
        details.put("applicationRef", app.getApplicationRef());
        details.put("status", app.getStatus() != null ? app.getStatus().name() : "");
        details.put("applicationType", app.getApplicationType() != null ? app.getApplicationType().name() : "NORMAL");

        // Branch information
        Map<String, Object> branchInfo = new HashMap<>();
        Branch branch = null;
        String customerBranchName = app.getBranchId() != null ? app.getBranchId() : "N/A";
        if (app.getBranchId() != null && !app.getBranchId().isEmpty()) {
            branch = branchRepository.findByBranchId(app.getBranchId()).orElse(null);
        }
        if (branch == null && app.getIfscCode() != null && !app.getIfscCode().isEmpty()) {
            branch = branchRepository.findByIfscCode(app.getIfscCode()).orElse(null);
        }
        if (branch == null && app.getBranchId() != null && !app.getBranchId().isEmpty()) {
            branch = branchRepository.findByBranchNameContaining(app.getBranchId()).orElse(null);
        }
        if (branch != null) {
            branchInfo.put("branchId", customerBranchName);
            branchInfo.put("branchName", customerBranchName);
            branchInfo.put("ifscCode", branch.getIfscCode());
            branchInfo.put("branchAddress", branch.getBranchAddress());
            branchInfo.put("branchCity", branch.getBranchCity());
            branchInfo.put("branchState", branch.getBranchState());
            branchInfo.put("branchPincode", branch.getBranchPincode());
            branchInfo.put("branchPhone", branch.getBranchPhone());
            branchInfo.put("branchEmail", branch.getBranchEmail());
        } else {
            branchInfo.put("branchId", customerBranchName);
            branchInfo.put("branchName", customerBranchName);
            branchInfo.put("ifscCode", app.getIfscCode() != null ? app.getIfscCode() : "N/A");
            branchInfo.put("branchAddress", "--");
            branchInfo.put("branchCity", "--");
            branchInfo.put("branchState", "--");
            branchInfo.put("branchPincode", "--");
            branchInfo.put("branchPhone", "--");
            branchInfo.put("branchEmail", "--");
        }
        details.put("branchInfo", branchInfo);

        // Account information
        Map<String, Object> accountInfo = new HashMap<>();
        accountInfo.put("accountNumber", app.getAccountNumber() != null ? app.getAccountNumber() : "N/A");
        accountInfo.put("accountType", app.getAccountType() != null ? app.getAccountType().name() : "SAVINGS");
        accountInfo.put("customerId", app.getCustomerId() != null ? app.getCustomerId() : "N/A");
        accountInfo.put("accountStatus", app.getAccountStatus() != null ? app.getAccountStatus().name() : "ACTIVE");
        accountInfo.put("accountOpeningDate", app.getReviewedAt());
        details.put("accountInfo", accountInfo);

        // Customer information
        Map<String, Object> customerInfo = new HashMap<>();
        customerInfo.put("fullName", app.getOcrName() != null ? app.getOcrName() : "");
        customerInfo.put("dateOfBirth", app.getOcrDob());
        customerInfo.put("gender", app.getGender() != null ? app.getGender() : "N/A");
        customerInfo.put("mobile", app.getMobile() != null ? app.getMobile() : "");
        customerInfo.put("email", app.getEmail() != null ? app.getEmail() : "");
        customerInfo.put("address", app.getOcrAddress() != null ? app.getOcrAddress() : "");
        details.put("customerInfo", customerInfo);

        // Identity documents (masked)
        Map<String, Object> identityInfo = new HashMap<>();
        identityInfo.put("aadhaarNumber", maskAadhaar(app.getOcrIdNumber()));
        identityInfo.put("panNumber", maskPan(app.getOcrPanNumber()));
        identityInfo.put("aadhaarFrontPath", app.getAadhaarFrontPath());
        identityInfo.put("aadhaarBackPath", app.getAadhaarBackPath());
        identityInfo.put("panCardPath", app.getPanCardPath());
        identityInfo.put("selfiePath", app.getSelfieFilePath());
        identityInfo.put("photoPath", app.getPhotoFilePath());
        details.put("identityInfo", identityInfo);

        // KYC details
        Map<String, Object> kycDetails = new HashMap<>();
        kycDetails.put("kycStatus", app.getStatus() != null ? app.getStatus().name() : "DRAFT");
        String reKycStatus = app.getReKycStatus();
        // If reKycStatus is not set, check if there's a newer RE_KYC app from this user
        if ((reKycStatus == null || reKycStatus.isEmpty()) && app.getUser() != null) {
            List<KYCApplication> userApps = kycApplicationRepository.findByUserIdOrderByIdDesc(app.getUser().getId());
            for (KYCApplication otherApp : userApps) {
                if (otherApp.getId() != app.getId()
                        && otherApp.getApplicationType() == KYCApplication.ApplicationType.RE_KYC) {
                    reKycStatus = otherApp.getReKycStatus() != null ? otherApp.getReKycStatus() : "INITIATED";
                    break;
                }
            }
        }
        kycDetails.put("reKycStatus", (reKycStatus != null && !reKycStatus.isEmpty()) ? reKycStatus : "N/A");
        kycDetails.put("applicationId", app.getId());
        kycDetails.put("applicationRef", app.getApplicationRef());
        kycDetails.put("submittedAt", app.getSubmittedAt());
        kycDetails.put("reviewedAt", app.getReviewedAt());
        details.put("kycDetails", kycDetails);

        // Verification results
        Map<String, Object> verification = new HashMap<>();
        Map<String, Object> ocrResult = new HashMap<>();
        ocrResult.put("name", app.getOcrName());
        ocrResult.put("dob", app.getOcrDob());
        ocrResult.put("idNumber", maskAadhaar(app.getOcrIdNumber()));
        ocrResult.put("panNumber", maskPan(app.getOcrPanNumber()));
        ocrResult.put("address", app.getOcrAddress());
        verification.put("ocr", ocrResult);

        Map<String, Object> faceResult = new HashMap<>();
        faceResult.put("matchPercentage", app.getFaceMatchPercentage());
        faceResult.put("livenessPassed", app.isLivenessPassed());
        verification.put("face", faceResult);

        Map<String, Object> riskResult = new HashMap<>();
        riskResult.put("score", app.getRiskScore());
        riskResult.put("level", app.getRiskLevel() != null ? app.getRiskLevel().name() : "LOW");
        verification.put("risk", riskResult);

        Map<String, Object> qrResult = new HashMap<>();
        qrResult.put("verified", app.getQrVerified());
        qrResult.put("status", app.getQrVerificationStatus() != null ? app.getQrVerificationStatus().name() : "SKIPPED");
        qrResult.put("matchPercentage", app.getQrMatchPercentage());

        // Get full QR verification result if available
        Optional<QRVerificationResult> latestQr = qrVerificationRepository.findFirstByApplicationIdOrderByVerifiedAtDesc(applicationId);
        if (latestQr.isPresent()) {
            QRVerificationResult qr = latestQr.get();
            Map<String, Object> qrFields = new HashMap<>();
            qrFields.put("name", Map.of("ocr", str(qr.getOcrName()), "qr", str(qr.getQrName()), "match", bool(qr.getNameMatch())));
            qrFields.put("dob", Map.of("ocr", str(qr.getOcrDob()), "qr", str(qr.getQrDob()), "match", bool(qr.getDobMatch())));
            qrFields.put("aadhaar", Map.of("ocr", str(qr.getOcrIdNumber()), "qr", str(qr.getQrIdNumber()), "match", bool(qr.getIdNumberMatch())));
            qrFields.put("pan", Map.of("ocr", str(qr.getOcrPanNumber()), "qr", str(qr.getQrPanNumber()), "match", bool(qr.getPanNumberMatch())));
            qrResult.put("fields", qrFields);
        }
        verification.put("qr", qrResult);
        details.put("verification", verification);

        // Documents
        Map<String, Object> documents = new HashMap<>();
        documents.put("selfiePath", app.getSelfieFilePath());
        documents.put("aadhaarFrontPath", app.getAadhaarFrontPath());
        documents.put("aadhaarBackPath", app.getAadhaarBackPath());
        documents.put("panCardPath", app.getPanCardPath());
        documents.put("docFilePath", app.getDocFilePath());
        details.put("documents", documents);

        // Timeline
        List<Map<String, Object>> timeline = new ArrayList<>();
        if (app.getCreatedAt() != null) {
            Map<String, Object> created = new HashMap<>();
            created.put("event", "Application Created"); created.put("date", app.getCreatedAt()); created.put("icon", "📝");
            timeline.add(created);
        }
        if (app.getSubmittedAt() != null) {
            Map<String, Object> submitted = new HashMap<>();
            submitted.put("event", "Application Submitted"); submitted.put("date", app.getSubmittedAt()); submitted.put("icon", "📤");
            timeline.add(submitted);
        }
        if (app.getReviewedAt() != null && app.getStatus() != null) {
            String reviewEvent = "APPROVED".equals(app.getStatus().name()) ? "Application Approved" : "Application Rejected";
            Map<String, Object> reviewEntry = new HashMap<>();
            reviewEntry.put("event", reviewEvent);
            reviewEntry.put("date", app.getReviewedAt());
            reviewEntry.put("icon", "APPROVED".equals(app.getStatus().name()) ? "✅" : "❌");
            if (app.getReviewNotes() != null && !app.getReviewNotes().isEmpty()) {
                reviewEntry.put("remarks", app.getReviewNotes());
            }
            timeline.add(reviewEntry);
        }
        if (app.getQrVerifiedAt() != null) {
            Map<String, Object> qrEvent = new HashMap<>();
            qrEvent.put("event", "QR Verification Completed"); qrEvent.put("date", app.getQrVerifiedAt()); qrEvent.put("icon", "📱");
            timeline.add(qrEvent);
        }
        details.put("timeline", timeline);

        // Device & session
        Map<String, Object> session = new HashMap<>();
        session.put("device", app.getDevice() != null ? app.getDevice() : "N/A");
        session.put("ipAddress", app.getIpAddress() != null ? app.getIpAddress() : "N/A");
        session.put("location", app.getLocation() != null ? app.getLocation() : "N/A");
        details.put("session", session);

        return details;
    }

    private String maskAadhaar(String aadhaar) {
        if (aadhaar == null || aadhaar.length() < 4) return aadhaar;
        return "XXXX-XXXX-" + aadhaar.substring(aadhaar.length() - 4);
    }

    private String maskPan(String pan) {
        if (pan == null || pan.length() < 4) return pan;
        return "XXXXX" + pan.substring(pan.length() - 4);
    }

    private String str(String s) {
        return s != null ? s : "";
    }

    private boolean bool(Boolean b) {
        return b != null && b;
    }
}
