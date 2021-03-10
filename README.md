# README #
**Python Version- 3.7**
This script was used in the fall of 2020 to take usage reports from the vendors we get individual subscriptions from and put them into a format we can ingest into LibInsight. Because of the way we pay these and the way LibInsight handles payment, we can't just load the JR1 reports from vendors.

We group titles we pay for as a package into the package name, then output a file for each subscription rather than each vendor (as I said, LibInsight applies costs at the vendor/platform level, so we break these out into individual 'platforms' of their own so we can get cost per use data and such).

The no_counter variable lists publishers who do not supply a COUNTER report, so we either do something special for their usage or we can't get it. We keep track of these so we don't accidentally generate a 0-use report.

Use
===
Works off a CLI (command-line interface). There are several requirements:

#### data directory
This directory should contain both the usage reports and a subscription spreadsheet, downloaded from WTCOX. This path can be relative to the directory the script is running from (./data). There are no name restrictions for the reports, as long as they are tab-delimited and have the suffix '.tsv'. The subscription spreadsheet does have a name restriction and must be tab-delimited: 'wtcox_no_header_fulfilled.txt'. As the name implies, the spreadsheet should not contain a header row.

 **Output**:
 
 * to ./data/output
    * a csv file for each platform formatted for upload to LibInsight.
 * to directory the script is running from (Three script reports to help validate output data: )
    * journals_with_automated_zero_usage.tsv
    * no_usage_reports_or_password_only.tsv
    * journals_with_no_issn.tsv