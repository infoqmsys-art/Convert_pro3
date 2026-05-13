package com.surveyportal.repo;

import com.surveyportal.domain.Site;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SiteRepository extends JpaRepository<Site, Long> {
  List<Site> findByOrganizationId(Long organizationId);
}
