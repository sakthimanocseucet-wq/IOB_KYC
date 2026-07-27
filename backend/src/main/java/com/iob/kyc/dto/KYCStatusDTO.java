package com.iob.kyc.dto;

import com.iob.kyc.model.KYCApplication;
import java.math.BigDecimal;
import java.time.LocalDateTime;

public class KYCStatusDTO {
    private Long id;
    private String applicationRef;
    private String docType;
    private String ocrName;
    private LocalDateTime ocrDob;
    private String ocrIdNumber;
    private String ocrPanNumber;
    private String ocrAddress;
    private String mobile;
    private String email;
    private String gender;
    private String ipAddress;
    private String device;
    private BigDecimal faceMatchPercentage;
    private boolean livenessPassed;
    private int riskScore;
    private String riskLevel;
    private String applicationType;
    private String status;
    private String reviewNotes;
    private Boolean qrVerified;
    private String qrVerificationStatus;
    private Double qrMatchPercentage;
    private LocalDateTime qrVerifiedAt;
    private LocalDateTime submittedAt;
    private LocalDateTime reviewedAt;
    private String accountNumber;
    private String customerId;
    private String accountType;
    private String accountStatus;
    private LocalDateTime accountOpeningDate;
    private String branchId;
    private String ifscCode;
    private String remarks;
    private String reKycStatus;
    private String challengeResults;
    private String challengeSequence;
    private Double qrFaceMatchScore;
    private String qrFaceMatchStatus;
    private Double qrFaceConfidence;
    private String docFilePath;
    private String aadhaarFrontPath;
    private String aadhaarBackPath;
    private String panCardPath;
    private String selfieFilePath;
    private String photoFilePath;
    private LocalDateTime verificationTimestamp;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    // User info
    private String userName;
    private String userEmail;
    private String userPhone;

    public static KYCStatusDTO fromEntity(KYCApplication app) {
        KYCStatusDTO dto = new KYCStatusDTO();
        dto.id = app.getId();
        dto.applicationRef = app.getApplicationRef();
        dto.docType = app.getDocType() != null ? app.getDocType().name() : null;
        dto.ocrName = app.getOcrName();
        dto.ocrDob = app.getOcrDob();
        dto.ocrIdNumber = app.getOcrIdNumber();
        dto.ocrPanNumber = app.getOcrPanNumber();
        dto.ocrAddress = app.getOcrAddress();
        dto.mobile = app.getMobile();
        dto.email = app.getEmail();
        dto.gender = app.getGender();
        dto.ipAddress = app.getIpAddress();
        dto.device = app.getDevice();
        dto.faceMatchPercentage = app.getFaceMatchPercentage();
        dto.livenessPassed = app.isLivenessPassed();
        dto.riskScore = app.getRiskScore();
        dto.riskLevel = app.getRiskLevel() != null ? app.getRiskLevel().name() : null;
        dto.applicationType = app.getApplicationType() != null ? app.getApplicationType().name() : null;
        dto.status = app.getStatus() != null ? app.getStatus().name() : null;
        dto.reviewNotes = app.getReviewNotes();
        dto.qrVerified = app.getQrVerified();
        dto.qrVerificationStatus = app.getQrVerificationStatus() != null ? app.getQrVerificationStatus().name() : null;
        dto.qrMatchPercentage = app.getQrMatchPercentage();
        dto.qrVerifiedAt = app.getQrVerifiedAt();
        dto.submittedAt = app.getSubmittedAt();
        dto.reviewedAt = app.getReviewedAt();
        dto.accountNumber = app.getAccountNumber();
        dto.customerId = app.getCustomerId();
        dto.accountType = app.getAccountType() != null ? app.getAccountType().name() : null;
        dto.accountStatus = app.getAccountStatus() != null ? app.getAccountStatus().name() : null;
        dto.accountOpeningDate = app.getAccountOpeningDate();
        dto.branchId = app.getBranchId();
        dto.ifscCode = app.getIfscCode();
        dto.remarks = app.getRemarks();
        dto.reKycStatus = app.getReKycStatus();
        dto.challengeResults = app.getChallengeResults();
        dto.challengeSequence = app.getChallengeSequence();
        dto.qrFaceMatchScore = app.getQrFaceMatchScore();
        dto.qrFaceMatchStatus = app.getQrFaceMatchStatus();
        dto.qrFaceConfidence = app.getQrFaceConfidence();
        dto.verificationTimestamp = app.getVerificationTimestamp();
        dto.createdAt = app.getCreatedAt();
        dto.updatedAt = app.getUpdatedAt();
        dto.docFilePath = app.getDocFilePath();
        dto.aadhaarFrontPath = app.getAadhaarFrontPath();
        dto.aadhaarBackPath = app.getAadhaarBackPath();
        dto.panCardPath = app.getPanCardPath();
        dto.selfieFilePath = app.getSelfieFilePath();
        dto.photoFilePath = app.getPhotoFilePath();

        if (app.getUser() != null) {
            dto.userName = (app.getUser().getFirstName() != null ? app.getUser().getFirstName() : "") +
                           (app.getUser().getLastName() != null ? " " + app.getUser().getLastName() : "");
            dto.userEmail = app.getUser().getEmail();
            dto.userPhone = app.getUser().getPhone();
        }

        return dto;
    }

    public Long getId() { return id; }
    public String getApplicationRef() { return applicationRef; }
    public String getDocType() { return docType; }
    public String getOcrName() { return ocrName; }
    public LocalDateTime getOcrDob() { return ocrDob; }
    public String getOcrIdNumber() { return ocrIdNumber; }
    public String getOcrPanNumber() { return ocrPanNumber; }
    public String getOcrAddress() { return ocrAddress; }
    public String getMobile() { return mobile; }
    public String getEmail() { return email; }
    public String getGender() { return gender; }
    public String getIpAddress() { return ipAddress; }
    public String getDevice() { return device; }
    public BigDecimal getFaceMatchPercentage() { return faceMatchPercentage; }
    public boolean isLivenessPassed() { return livenessPassed; }
    public int getRiskScore() { return riskScore; }
    public String getRiskLevel() { return riskLevel; }
    public String getApplicationType() { return applicationType; }
    public String getStatus() { return status; }
    public String getReviewNotes() { return reviewNotes; }
    public Boolean getQrVerified() { return qrVerified; }
    public String getQrVerificationStatus() { return qrVerificationStatus; }
    public Double getQrMatchPercentage() { return qrMatchPercentage; }
    public LocalDateTime getQrVerifiedAt() { return qrVerifiedAt; }
    public LocalDateTime getSubmittedAt() { return submittedAt; }
    public LocalDateTime getReviewedAt() { return reviewedAt; }
    public String getAccountNumber() { return accountNumber; }
    public String getCustomerId() { return customerId; }
    public String getAccountType() { return accountType; }
    public String getAccountStatus() { return accountStatus; }
    public LocalDateTime getAccountOpeningDate() { return accountOpeningDate; }
    public String getBranchId() { return branchId; }
    public String getIfscCode() { return ifscCode; }
    public String getRemarks() { return remarks; }
    public String getReKycStatus() { return reKycStatus; }
    public String getChallengeResults() { return challengeResults; }
    public String getChallengeSequence() { return challengeSequence; }
    public Double getQrFaceMatchScore() { return qrFaceMatchScore; }
    public String getQrFaceMatchStatus() { return qrFaceMatchStatus; }
    public Double getQrFaceConfidence() { return qrFaceConfidence; }
    public LocalDateTime getVerificationTimestamp() { return verificationTimestamp; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public String getDocFilePath() { return docFilePath; }
    public String getAadhaarFrontPath() { return aadhaarFrontPath; }
    public String getAadhaarBackPath() { return aadhaarBackPath; }
    public String getPanCardPath() { return panCardPath; }
    public String getSelfieFilePath() { return selfieFilePath; }
    public String getPhotoFilePath() { return photoFilePath; }
    public String getUserName() { return userName; }
    public String getUserEmail() { return userEmail; }
    public String getUserPhone() { return userPhone; }
}
