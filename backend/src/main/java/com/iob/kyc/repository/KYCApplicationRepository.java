package com.iob.kyc.repository;

import com.iob.kyc.model.KYCApplication;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface KYCApplicationRepository extends JpaRepository<KYCApplication, Long> {

    @EntityGraph(attributePaths = {"user", "reviewedBy"})
    List<KYCApplication> findByUserIdOrderByIdDesc(Long userId);

    @EntityGraph(attributePaths = {"user", "reviewedBy"})
    List<KYCApplication> findByStatus(KYCApplication.Status status);

    @EntityGraph(attributePaths = {"user", "reviewedBy"})
    Page<KYCApplication> findByApplicationType(KYCApplication.ApplicationType applicationType, Pageable pageable);

    @EntityGraph(attributePaths = {"user", "reviewedBy"})
    Page<KYCApplication> findAll(Pageable pageable);

    @Override
    @EntityGraph(attributePaths = {"user", "reviewedBy"})
    List<KYCApplication> findAll();

    @Query("SELECT k FROM KYCApplication k LEFT JOIN FETCH k.user LEFT JOIN FETCH k.reviewedBy WHERE k.id = :id")
    Optional<KYCApplication> findByIdWithUser(@Param("id") Long id);

    @Override
    @Query("SELECT k FROM KYCApplication k WHERE k.id = :id")
    Optional<KYCApplication> findById(@Param("id") Long id);

    List<KYCApplication> findByRiskLevel(KYCApplication.RiskLevel riskLevel);

    long countByStatus(KYCApplication.Status status);

    @Query("SELECT COUNT(k) FROM KYCApplication k WHERE k.submittedAt >= :since")
    long countSubmittedSince(@Param("since") LocalDateTime since);

    @Query("SELECT COUNT(k) FROM KYCApplication k WHERE k.status = :status AND k.submittedAt >= :since")
    long countByStatusSince(@Param("status") KYCApplication.Status status, @Param("since") LocalDateTime since);

    @Query("SELECT k FROM KYCApplication k WHERE k.submittedAt >= :since ORDER BY k.submittedAt DESC")
    List<KYCApplication> findSubmittedSince(@Param("since") LocalDateTime since);

    @Query("SELECT k FROM KYCApplication k WHERE k.ocrIdNumber = :idNumber AND k.id <> :excludeId")
    List<KYCApplication> findByOcrIdNumberExcludingId(@Param("idNumber") String idNumber, @Param("excludeId") Long excludeId);

    @Query("SELECT k FROM KYCApplication k WHERE k.ocrPanNumber = :panNumber AND k.id <> :excludeId")
    List<KYCApplication> findByOcrPanNumberExcludingId(@Param("panNumber") String panNumber, @Param("excludeId") Long excludeId);

    @Query("SELECT k FROM KYCApplication k WHERE k.ipAddress = :ipAddress AND k.id <> :excludeId")
    List<KYCApplication> findByIpAddressExcludingId(@Param("ipAddress") String ipAddress, @Param("excludeId") Long excludeId);

    @Query("SELECT k FROM KYCApplication k WHERE k.mobile = :mobile AND k.id <> :excludeId AND k.status <> 'REJECTED'")
    List<KYCApplication> findByMobileExcludingId(@Param("mobile") String mobile, @Param("excludeId") Long excludeId);

    @Query("SELECT COUNT(k) FROM KYCApplication k WHERE k.mobile = :mobile AND k.status <> 'REJECTED'")
    long countByMobile(@Param("mobile") String mobile);

    @EntityGraph(attributePaths = {"user", "reviewedBy"})
    @Query("SELECT k FROM KYCApplication k WHERE k.reviewedBy.employeeId = :employeeId ORDER BY k.id DESC")
    List<KYCApplication> findByAssignedEmployee(@Param("employeeId") String employeeId);

    @EntityGraph(attributePaths = {"user", "reviewedBy"})
    @Query("SELECT k FROM KYCApplication k WHERE k.reviewedBy.employeeId = :employeeId AND k.status = :status ORDER BY k.id DESC")
    List<KYCApplication> findByAssignedEmployeeAndStatus(@Param("employeeId") String employeeId, @Param("status") KYCApplication.Status status);

    @EntityGraph(attributePaths = {"user", "reviewedBy"})
    Page<KYCApplication> findByStatus(KYCApplication.Status status, org.springframework.data.domain.Pageable pageable);
}
