Request URL
https://portal.ecotricity.co.nz/powercommerce/eco/fo/portal/analysis/initData
Request Method
POST
Status Code
200 OK
Remote Address
172.67.74.193:443
Referrer Policy
strict-origin-when-cross-origin
access-control-allow-headers
Origin, X-Requested-With, Content-Type, Accept
access-control-allow-methods
POST, GET, OPTIONS, DELETE
access-control-allow-origin
*
access-control-max-age
3600
cache-control
no-cache
cache-control
no-store
cf-cache-status
DYNAMIC
cf-ray
a2a632277e6dd9aa-AKL
content-encoding
br
content-type
application/json;charset=UTF-8
date
Thu, 13 Aug 2026 08:02:09 GMT
expires
Thu, 01 Jan 1970 00:00:00 GMT
nel
{"report_to":"cf-nel","success_fraction":0.0,"max_age":604800}
p3p
CP="CAO PSA OUR"
pragma
no-cache
report-to
{"group":"cf-nel","max_age":604800,"endpoints":[{"url":"https://a.nel.cloudflare.com/report/v4?s=7Dr5oeoJUU3TYaa7gHwgejtQDnuv9hyHt45uDlRdglI9UF9%2BEpRz%2FeCIeLb2K%2BsS910eNCw1YBAMqcQkY06O7siMFwt2NsCW5414BPY7omiKq%2F0iVR%2FohbBRBqTFZ5bgdxIGhZEEE6Z%2F"}]}
server
cloudflare
x-content-type-options
nosniff
x-frame-options
SAMEORIGIN
x-ua-compatible
IE=Edge
x-xss-protection
1; mode=block
:authority
portal.ecotricity.co.nz
:method
POST
:path
/powercommerce/eco/fo/portal/analysis/initData
:scheme
https
accept
application/json, text/javascript, */*; q=0.01
accept-encoding
gzip, deflate, br, zstd
accept-language
en-US,en;q=0.9
content-length
145
content-type
application/json
cookie
JSESSIONID=C2NxEUvjwBgE-nLFyOr1_KLiafQnT2mwPGzP_CyX.ecotitc-asp; intercom-id-dnj7ka47=ea048ec1-8daa-48f6-84db-e00eca5f035a; intercom-session-dnj7ka47=; intercom-device-id-dnj7ka47=ed242afe-6100-4a54-8b4a-9ec7d43194a1
origin
https://portal.ecotricity.co.nz
priority
u=1, i
referer
https://portal.ecotricity.co.nz/powercommerce/eco/fo/portal/consumptionDetails
sec-ch-ua
"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"
sec-ch-ua-mobile
?0
sec-ch-ua-platform
"Windows"
sec-fetch-dest
empty
sec-fetch-mode
cors
sec-fetch-site
same-origin
user-agent
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
x-requested-with
XMLHttpRequest



PAYLOAD
{"fetchCurrentIndicator":true,"fetchInstallation":false,"fetchLastImport":true,"fetchEnergyPerformanceIndicator":true,"fetchImsysFeatures":false}

RESPONSE
{
  "featureDescriptions" : {
    "EMISSION|POWER_ACTIVE_PURCHASE_CONSUMPTION|Carbon Savings" : {
      "displayName" : "Carbon Savings",
      "unit" : {
        "unit" : "kg",
        "displayName" : "kg"
      },
      "baseType" : {
        "type" : "EMISSION",
        "displayName" : "EMISSION"
      }
    },
    "POWER_ACTIVE_PURCHASE_CONSUMPTION" : {
      "displayName" : "Electricity consumed",
      "unit" : {
        "unit" : "(W.h).1000",
        "displayName" : "kWh"
      },
      "media" : {
        "mediaType" : "POWER",
        "displayName" : "Power"
      }
    }
  },
  "currentIndicator" : {
    "indicatorID" : "470f2d40-42ca-11f1-9ba3-020017005c7e",
    "indicatorType" : "INDICATOR_GROUP",
    "displayName" : "1002209564UN05C",
    "lastImportDate" : "2026-08-13T04:09:08.858+02:00",
    "features" : {
      "EMISSION|POWER_ACTIVE_PURCHASE_CONSUMPTION|Carbon Savings" : [ {
        "nativeGranularityType" : "HALF_HOUR",
        "aggregated" : false,
        "measuredValueRange" : {
          "2026-05-04T02:00:00.000+02:00" : "2026-08-11T01:00:00.000+02:00"
        }
      } ],
      "POWER_ACTIVE_PURCHASE_CONSUMPTION" : [ {
        "nativeGranularityType" : "HALF_HOUR",
        "aggregated" : false,
        "measuredValueRange" : {
          "2026-05-04T02:00:00.000+02:00" : "2026-08-11T01:00:00.000+02:00"
        }
      } ]
    }
  }
}