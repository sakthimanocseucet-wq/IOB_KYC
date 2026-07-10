package com.iob.kyc.model;

import jakarta.persistence.*;
import lombok.*;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "kyc_applications")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class KYCApplication {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    @JsonIgnoreProperties({"hibernateLazyInitializer", "passwordHash"})
    private User user;

    @Column(name = "application_ref", unique = true, nullable = false)
    private String applicationRef;

    @Enumerated(EnumType.STRING)
    @Column(name = "doc_type", nullable = false)
    private DocType docType;

    @Column(name = "doc_file_path")
    private String docFilePath;

    @Column(name = "aadhaar_front_path")
    private String aadhaarFrontPath;

    @Column(name = "aadhaar_back_path")
    private String aadhaarBackPath;

    @Column(name = "pan_card_path")
    private String panCardPath;

    @Column(name = "selfie_file_path")
    private String selfieFilePath;

    @Column(name = "photo_file_path")
    private String photoFilePath;

    @Column(name = "ocr_name")
    private String ocrName;

    @Column(name = "ocr_dob")
    private LocalDateTime ocrDob;

    @Column(name = "ocr_id_number")
    private String ocrIdNumber;

    @Column(name = "ocr_pan_number")
    private String ocrPanNumber;

    @Column(name = "ocr_address")
    private String ocrAddress;

    @Column(name = "mobile")
    private String mobile;

    @Column(name = "email")
    private String email;

    @Column(name = "ip_address")
    private String ipAddress;

    @Column(name = "device", length = 500)
    private String device;

    @Column(name = "location", length = 500)
    private String location;

    @Column(name = "face_match_percentage")
    private BigDecimal faceMatchPercentage;

    @Column(name = "liveness_passed")
    private boolean livenessPassed;

    @Column(name = "risk_score")
    private int riskScore;

    @Enumerated(EnumType.STRING)
    @Column(name = "risk_level")
    @Builder.Default
    private RiskLevel riskLevel = RiskLevel.LOW;

    @Enumerated(EnumType.STRING)
    @Column(name = "application_type", nullable = false)
    @Builder.Default
    private ApplicationType applicationType = ApplicationType.NORMAL;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private Status status = Status.DRAFT;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "reviewed_by")
    @JsonIgnoreProperties({"hibernateLazyInitializer", "passwordHash"})
    private Employee reviewedBy;

    @Column(name = "review_notes")
    private String reviewNotes;

    @Column(name = "qr_verified")
    private Boolean qrVerified;

    @Enumerated(EnumType.STRING)
    @Column(name = "qr_verification_status")
    private QRStatus qrVerificationStatus;

    @Column(name = "qr_match_percentage")
    private Double qrMatchPercentage;

    @Column(name = "qr_verified_at")
    private LocalDateTime qrVerifiedAt;

    @Column(name = "submitted_at")
    private LocalDateTime submittedAt;

    @Column(name = "reviewed_at")
    private LocalDateTime reviewedAt;

    @Column(name = "account_number", length = 30)
    private String accountNumber;

    @Column(name = "customer_id", length = 30)
    private String customerId;

    @Enumerated(EnumType.STRING)
    @Column(name = "account_type")
    private AccountType accountType;

    @Enumerated(EnumType.STRING)
    @Column(name = "account_status")
    @Builder.Default
    private AccountStatus accountStatus = AccountStatus.ACTIVE;

    @Column(name = "account_opening_date")
    private LocalDateTime accountOpeningDate;

    @Column(name = "gender", length = 20)
    private String gender;

    @Column(name = "branch_id", length = 50)
    private String branchId;

    @Column(name = "assigned_employee_id", length = 50)
    private String assignedEmployeeId;

    @Column(name = "ifsc_code", length = 20)
    private String ifscCode;

    @Column(name = "remarks", length = 1000)
    private String remarks;

    @Lob
    @Column(name = "selfie_base64", columnDefinition = "LONGTEXT")
    private String selfieBase64;

    @Lob
    @Column(name = "photo_base64", columnDefinition = "LONGTEXT")
    private String photoBase64;

    @Lob
    @Column(name = "aadhaar_front_base64", columnDefinition = "LONGTEXT")
    private String aadhaarFrontBase64;

    @Lob
    @Column(name = "aadhaar_back_base64", columnDefinition = "LONGTEXT")
    private String aadhaarBackBase64;

    @Lob
    @Column(name = "pan_card_base64", columnDefinition = "LONGTEXT")
    private String panCardBase64;

    @Lob
    @Column(name = "doc_file_base64", columnDefinition = "LONGTEXT")
    private String docFileBase64;

    @Column(name = "re_kyc_status", length = 30)
    private String reKycStatus;

    @Column(name = "last_reviewed_at")
    private LocalDateTime lastReviewedAt;

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
        if (applicationRef == null) {
            applicationRef = "IOB-KYC-" + System.currentTimeMillis() + "-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        }
    }

    @PreUpdate
    protected void onUpdate() { updatedAt = LocalDateTime.now(); }

    public enum DocType { AADHAAR, PAN }
    public enum RiskLevel { LOW, MEDIUM, HIGH }
    public enum Status { DRAFT, PENDING, UNDER_REVIEW, APPROVED, REJECTED, SUPERSEDED }
    public enum ApplicationType { NORMAL, RE_KYC }
    public enum AccountType { SAVINGS, CURRENT }
    public enum AccountStatus { ACTIVE, INACTIVE, FROZEN, CLOSED }

    public void setLivenessPassed(Boolean livenessPassed) {
        this.livenessPassed = livenessPassed != null && livenessPassed;
    }
}
