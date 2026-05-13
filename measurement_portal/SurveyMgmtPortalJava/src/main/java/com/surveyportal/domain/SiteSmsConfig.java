package com.surveyportal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "site_sms_config")
public class SiteSmsConfig {

  @Id
  @Column(name = "site_id")
  private Long siteId;

  @Column(nullable = false)
  private Integer enabled = 0;

  @Column(name = "message_template")
  private String messageTemplate;

  @Column(name = "time_from")
  private String timeFrom;

  @Column(name = "time_to")
  private String timeTo;

  @Column(name = "updated_at")
  private String updatedAt;

  public Long getSiteId() {
    return siteId;
  }

  public void setSiteId(Long siteId) {
    this.siteId = siteId;
  }

  public Integer getEnabled() {
    return enabled;
  }

  public void setEnabled(Integer enabled) {
    this.enabled = enabled;
  }

  public String getMessageTemplate() {
    return messageTemplate;
  }

  public void setMessageTemplate(String messageTemplate) {
    this.messageTemplate = messageTemplate;
  }

  public String getTimeFrom() {
    return timeFrom;
  }

  public void setTimeFrom(String timeFrom) {
    this.timeFrom = timeFrom;
  }

  public String getTimeTo() {
    return timeTo;
  }

  public void setTimeTo(String timeTo) {
    this.timeTo = timeTo;
  }

  public String getUpdatedAt() {
    return updatedAt;
  }

  public void setUpdatedAt(String updatedAt) {
    this.updatedAt = updatedAt;
  }
}
