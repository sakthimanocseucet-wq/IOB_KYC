package com.iob.kyc.model;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
@Entity
@Table(name = "otp_codes")
public class OtpCode {

    public enum Purpose {
        LOGIN, REGISTER, KYC, PASSWORD_RESET
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Long userId;

    private String identifier;

    @Column(nullable = false)
    private String otpCode;

    @Enumerated(EnumType.STRING)
    private Purpose purpose;

    private boolean used;

    private LocalDateTime expiresAt;

    private LocalDateTime createdAt;
}
