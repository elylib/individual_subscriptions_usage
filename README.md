# Individual Subscriptions Usage

This script was used in the fall of 2017 to take usage reports from the vendors we get individual subscriptions from and put them into a format we can ingest into LibInsight. Because of the way we pay these and the way LibInsight handles payment, we can't just load the JR1 reports from vendors.

We group titles we pay for as a package into the package name, then output a file for each subscription rather than each vendor (as I said, LibInsight applies costs at the vendor/platform level, so we break these out into individual 'platforms' of their own so we can get cost per use data and such).

The no_counter variable lists publishers who do not supply a COUNTER report, so we either do something special for their usage or we can't get it. We keep track of these so we don't accidentally generate a 0-use report. 