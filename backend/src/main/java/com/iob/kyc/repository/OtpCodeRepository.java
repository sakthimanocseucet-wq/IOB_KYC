package com.iob.kyc.repository;

import com.iob.kyc.model.OtpCode;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.Optional;

public interface OtpCodeRepository extends JpaRepository<OtpCode, Long> {

    Optional<OtpCode> findTopByIdentifierAndPurposeAndUsedFalseAndExpiresAtAfterOrderByCreatedAtDesc(
            String identifier, OtpCode.Purpose purpose, LocalDateTime now);
}
