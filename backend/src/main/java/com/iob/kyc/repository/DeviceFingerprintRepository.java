package com.iob.kyc.repository;

import com.iob.kyc.model.DeviceFingerprint;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface DeviceFingerprintRepository extends JpaRepository<DeviceFingerprint, Long> {

    Optional<DeviceFingerprint> findByUserId(Long userId);

    Optional<DeviceFingerprint> findByFingerprintHash(String fingerprintHash);
}
