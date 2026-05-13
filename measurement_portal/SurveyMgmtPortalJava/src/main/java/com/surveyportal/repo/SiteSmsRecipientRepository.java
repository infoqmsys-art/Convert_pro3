package com.surveyportal.repo;

import com.surveyportal.domain.SiteSmsRecipient;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SiteSmsRecipientRepository extends JpaRepository<SiteSmsRecipient, Long> {
  List<SiteSmsRecipient> findBySiteIdOrderBySortOrderAscIdAsc(Long siteId);

  void deleteByIdAndSiteId(Long id, Long siteId);
}
