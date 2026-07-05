package com.iob.kyc.model;

import jakarta.persistence.*;
import lombok.*;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

@Entity
@Table(name = "qr_verification_results")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class QRVerificationResult {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "application_id", nullable = false)
    @JsonIgnoreProperties({"hibernateLazyInitializer", "user"})
    private KYCApplication application;

    @Column(name = "qr_detected", nullable = false)
    private boolean qrDetected;

    @Enumerated(EnumType.STRING)
    @Column(name = "verification_status", nullable = false)
    private QRStatus verificationStatus;

    @Column(name = "match_percentage")
    private double matchPercentage;

    @Column(name = "document_type", nullable = false)
    private String documentType;

    @Column(name = "ocr_name", length = 200)
    private String ocrName;

    @Column(name = "qr_name", length = 200)
    private String qrName;

    @Column(name = "name_match")
    private Boolean nameMatch;

    @Column(name = "ocr_dob", length = 20)
    private String ocrDob;

    @Column(name = "qr_dob", length = 20)
    private String qrDob;

    @Column(name = "dob_match")
    private Boolean dobMatch;

    @Column(name = "ocr_id_number", length = 20)
    private String ocrIdNumber;

    @Column(name = "qr_id_number", length = 20)
    private String qrIdNumber;

    @Column(name = "id_number_match")
    private Boolean idNumberMatch;

    @Column(name = "ocr_pan_number", length = 20)
    private String ocrPanNumber;

    @Column(name = "qr_pan_number", length = 20)
    private String qrPanNumber;

    @Column(name = "pan_number_match")
    private Boolean panNumberMatch;

    @Column(name = "qr_raw_data", length = 1000)
    private String qrRawData;

    @Column(name = "message", length = 500)
    private String message;

    @Column(name = "processing_time_ms")
    private double processingTimeMs;

    @Column(name = "verified_at", nullable = false)
    private LocalDateTime verifiedAt;

    @PrePersist
    protected void onCreate() {
        verifiedAt = LocalDateTime.now();
    }

    @JsonProperty("results")
    public Map<String, Map<String, Object>> getResults() {
        Map<String, Map<String, Object>> results = new HashMap<>();

        Map<String, Object> nameMap = new HashMap<>();
        nameMap.put("ocr", ocrName != null ? ocrName : "");
        nameMap.put("qr", qrName != null ? qrName : "");
        nameMap.put("match", nameMatch != null && nameMatch);
        results.put("name", nameMap);

        Map<String, Object> dobMap = new HashMap<>();
        dobMap.put("ocr", ocrDob != null ? ocrDob : "");
        dobMap.put("qr", qrDob != null ? qrDob : "");
        dobMap.put("match", dobMatch != null && dobMatch);
        results.put("dob", dobMap);

        Map<String, Object> aadhaarMap = new HashMap<>();
        aadhaarMap.put("ocr", ocrIdNumber != null ? ocrIdNumber : "");
        aadhaarMap.put("qr", qrIdNumber != null ? qrIdNumber : "");
        aadhaarMap.put("match", idNumberMatch != null && idNumberMatch);
        results.put("aadhaar_number", aadhaarMap);

        Map<String, Object> panMap = new HashMap<>();
        panMap.put("ocr", ocrPanNumber != null ? ocrPanNumber : "");
        panMap.put("qr", qrPanNumber != null ? qrPanNumber : "");
        panMap.put("match", panNumberMatch != null && panNumberMatch);
        results.put("pan_number", panMap);

        return results;
    }
}
