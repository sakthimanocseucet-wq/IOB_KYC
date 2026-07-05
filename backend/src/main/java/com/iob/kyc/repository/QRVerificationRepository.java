package com.iob.kyc.repository;

import com.iob.kyc.model.QRStatus;
import com.iob.kyc.model.QRVerificationResult;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface QRVerificationRepository extends JpaRepository<QRVerificationResult, Long> {

    List<QRVerificationResult> findByApplicationIdOrderByVerifiedAtDesc(Long applicationId);

    Optional<QRVerificationResult> findFirstByApplicationIdOrderByVerifiedAtDesc(Long applicationId);

    @Query("SELECT q FROM QRVerificationResult q WHERE q.application.id = :applicationId AND q.verificationStatus = :status ORDER BY q.verifiedAt DESC")
    List<QRVerificationResult> findByApplicationIdAndStatus(@Param("applicationId") Long applicationId,
                                                             @Param("status") QRStatus status);

    boolean existsByApplicationIdAndVerificationStatus(Long applicationId, QRStatus status);
}
