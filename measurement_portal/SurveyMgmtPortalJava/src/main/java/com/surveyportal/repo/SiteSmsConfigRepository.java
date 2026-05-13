package com.surveyportal.repo;

import com.surveyportal.domain.SiteSmsConfig;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SiteSmsConfigRepository extends JpaRepository<SiteSmsConfig, Long> {
  Optional<SiteSmsConfig> findBySiteId(Long siteId);
}
