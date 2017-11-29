#!/usr/bin/env python3
"""
Module assumes a file structure with a data directory with an output directory inside it.
"""

from collections import defaultdict
import csv
import datetime
import glob
import os.path
from typing import Union, Pattern, Iterable

import pycounter

no_counter = {'American Association for State & Local History',
              'American Association of School Administrators', 'American Ceramic Society', 'American Federation of Teachers, AFL-CIO',
              'American Library Association', 'Artforum International', 'Association for Supervision & Curriculum Development',
              'Botanical Society of America', 'College Art Association of America', 'Coyne & Blanchard Inc.',
              'Current History', 'Foreign Policy', 'Harpers Magazine Foundation', 'Harvard Business School',
              'Harvard Health Publications', 'Institute for Social & Cultural Communications',
              'International Association of Chiefs of Police', 'Mansueto Ventures LLC', 'Media Source Inc',
              'National Association of Elementary School Principals', 'National Recreation & Park Association',
              'New Republic', 'New York State Society of Certified Public Accountants', 'Newbay Media LLC',
              'North American Society for Sport History', 'Penton Aviation Week Intelligence Network',
              'Sagamore Publishing LLS', 'Scriptorium Press, Inc.', 'The American Institute for Social Justice',
              'The Instrumentalist Publishing Company', 'The Society for History Education, Inc.', 'Times Supplement LTD',
              'ACTE Publications', 'Against the Grain'}

special_cases = {'Edizioni Minerva Medica', 'Chronicle of Higher Education', 'Philosophy Documentation Center'}


def get_journals_and_no_issns_from_wtcox(wtcox_tsv_path: str, journals_to_ignore: set) -> (dict, set, dict):
    """
    Take a tsv file from WTCox and read in all non-package entries that have an ISSN.

    Ignores entries without 'Online' as access identifier because 'Digital' is in report but is for magazines with
    password-only access, which basically excludes us from using it.

    9999-9994 is WTCox's way of saying it's a package identifier and not an actual publication.

    We pay as a package, so in determining what to call journals we collapse individual titles into their
    package name so in LibInsight we can see what we pay per unit of payment. We also only take the first part
    of a colonized title because the colon was messing up file names. Hence the
    (package if package else title).split(':')[0] ugliness.

    :param wtcox_tsv_path: path to the wtcox file containing our subscription information
    :param journals_to_ignore: an set of journal publishers known to not have usage, either because they provide
        access by password only, which doesn't work for us, or they just don't have reports
    :return: a pair containing a dict of journal titles index by issn and a set of journal titles that do not
        have an issn in WTCox.
    """
    issn_title = dict()
    no_issn = set()
    no_usage = dict()
    with open(wtcox_tsv_path, 'r') as r:
        for x in csv.reader(r, delimiter='\t'):
            title, issn, package, access, publisher = x[0].strip(), x[11].strip(), x[3].strip(), x[1].strip(), x[12]
            if publisher not in journals_to_ignore:
                no_usage[publisher] = title

            if not issn:
                no_issn.add(title)
            elif not issn == '9999-9994' and 'online' in access.lower() and publisher not in special_cases:
                issn_title[issn] = (package if package else title).split(':')[0]
    return issn_title, no_issn, no_usage


def get_usage_stats_from_wtcox_journals(journals_from_wtcox: dict, path_to_usage_reports: Union[str, Pattern]) -> dict:
    """
    Take an issn-indexed dict of titles and a path to Counter 4 reports and make a dict of dicts indexed as below.

    First index is the title of a journal, which holds a dict indexed by usage dates (months, basically), which holds
    the amount of use for that month.

    Checks against ISSN, may add a normalized title check for good measure.

    dict[title_of_journal][date_of_usage] = amount_of_use

    :param journals_from_wtcox: issn-indexed dict of journal titles to check usage of
    :param path_to_usage_reports: a glob-able string/regex to find all the usage reports to check against
    :return: A dict indexed as above
    """
    usage_reports = defaultdict(lambda: defaultdict(int))
    for fn in glob.glob(path_to_usage_reports):
        try:
            report = pycounter.report.parse(fn)
        except (pycounter.exceptions.UnknownReportTypeError, ValueError):
            print(fn)
            raise
        for journal in report:
            if getattr(journal, 'issn', '') in journals_from_wtcox:
                for x in journal:
                    usage_reports[journals_from_wtcox[journal.issn]][x[0]] += x[2]
    return usage_reports


def fill_in_missing_dates(usage: dict, dates: Iterable) -> dict:
    """
    Take a usage report and add in the missing years.

    This is for some journals that are not included in certain years' reports because they had no use. Even though
    Counter technically requires zero-use titles to be represented, they aren't a lot of the time. This does not
    attempt to determine if a journal is left out entirely, it just checks journals already there.

    :param usage: a dict of usage data
    :param dates: an iterable of date objects
    :return: an updated usage object
    """
    for title, uses in usage.items():
        for date in dates:
            if date not in uses:
                uses[date] = 0
    return usage


def fill_in_missing_journals(from_wtcox: dict, usage: dict, dates: Iterable) -> (dict, list):
    """
    Check WTCox list against a usage report and fill in any missing journals with 0 usages for dates given.

    We also  give back the not_found list so we can manually double check to make sure there just wasn't an ISSN match.
    Sanity checks.

    :param from_wtcox: issn-indexed dict of journal titles
    :param usage: usage report dict
    :param dates: an iterable of date objects
    :return: An updated usage report along with a list of what was updated for sanity checks
    """
    not_found = list()
    for title in from_wtcox.values():
        if title not in usage:
            not_found.append(title)
            for date in dates:
                usage[title][date] = 0
    return usage, not_found


def write_usage_to_file(usage: dict):
    """Write each journal's usage to a file for upload to LibInsight."""
    for title, use in usage.items():
        with open(os.path.join('data', 'output', title + '.csv'), 'w', encoding='UTF-8', newline='') as w:
            writer = csv.writer(w)
            writer.writerow(('Date', 'Downloads', 'Searches', 'Sessions', 'Views', 'Clicks'))
            for month in sorted(use):
                writer.writerow((month.strftime('%Y-%m-%d'), use[month], 0, 0, 0, 0))


def write_journals_not_found_to_file(not_found: Iterable):
    """Keep track of the journals we couldn't find any usage for for sanity checks."""
    with open('journals_with_automated_zero_usage.tsv', 'w', encoding='utf-8', newline='') as w:
        writer = csv.writer(w, delimiter='\t')
        for journal in not_found:
            writer.writerow(journal)


def write_journals_with_no_counter_to_file(no_counter: dict):
    """Keep track of journals that have zero usage because they don't have usage reports or are password-only."""
    with open('no_usage_reports_or_password_only.tsv', 'w', encoding='utf-8', newline='') as w:
        writer = csv.writer(w, delimiter='\t')
        writer.writerow(('Publisher', 'Title'))
        for publisher, title in no_counter.items():
            writer.writerow((publisher, title))


def write_journals_with_no_issn_to_file(no_issns: Iterable):
    with open('journals_with_no_issn.tsv', 'w', encoding='utf-8', newline='') as w:
        writer = csv.writer(w, delimiter='\t')
        for title in no_issns:
            writer.writerow((title,))


if __name__ == '__main__':
    dates = [datetime.date(year, month, 1) for month in range(1, 13) for year in range(2015, 2017)]
    dates.extend(datetime.date(2017, month, 1) for month in range(1, 10))

    wtcox_journals, journals_with_no_issn, ignored = get_journals_and_no_issns_from_wtcox(
        os.path.join('data', 'wtcox_no_header_fulfilled.txt'),
        no_counter)
    usage = get_usage_stats_from_wtcox_journals(wtcox_journals, os.path.join('data', '*.tsv'))
    usage = fill_in_missing_dates(usage, dates)
    usage, not_found = fill_in_missing_journals(wtcox_journals, usage, dates)
    write_usage_to_file(usage)
    write_journals_not_found_to_file(not_found)
    write_journals_with_no_counter_to_file(ignored)
    write_journals_with_no_issn_to_file(journals_with_no_issn)
    print("Not found: " + str(len(not_found)))
    print(str(len(not_found)) + '/' + str(len(usage)))
    assert len(set(wtcox_journals.values())) == len(usage)
