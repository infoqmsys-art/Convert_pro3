package com.surveyportal;

import com.surveyportal.config.SurveyProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(SurveyProperties.class)
public class SurveyPortalApplication {

  public static void main(String[] args) {
    SpringApplication.run(SurveyPortalApplication.class, args);
  }
}
