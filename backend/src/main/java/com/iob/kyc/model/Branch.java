package com.iob.kyc.model;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "branches")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Branch {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "branch_id", unique = true, nullable = false, length = 50)
    private String branchId;

    @Column(name = "branch_name", nullable = false, length = 200)
    private String branchName;

    @Column(name = "ifsc_code", length = 20)
    private String ifscCode;

    @Column(name = "branch_address", length = 500)
    private String branchAddress;

    @Column(name = "branch_city", length = 100)
    private String branchCity;

    @Column(name = "branch_state", length = 100)
    private String branchState;

    @Column(name = "branch_pincode", length = 10)
    private String branchPincode;

    @Column(name = "branch_phone", length = 20)
    private String branchPhone;

    @Column(name = "branch_email", length = 200)
    private String branchEmail;

    @Column(name = "is_active")
    @Builder.Default
    private boolean active = true;

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}
