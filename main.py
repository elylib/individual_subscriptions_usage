#!/usr/bin/env python3
"""
Module assumes a file structure with a data directory with an output directory inside it.
"""

from collections import defaultdict
import csv
import datetime
import glob
import os.path
from typing import Iterable, List, Dict, Set, AnyStr, NewType, Union, Pattern

import pycounter


Path = Union[AnyStr, bytes, Pattern]
ISSN = NewType('ISSN', AnyStr)
Title = NewType('Title', AnyStr)
Month = NewType('Month', datetime.date)
Usage = NewType('Usage', int)
UsageReport = NewType('UsageReport', Dict[Title, Dict[Month, Usage]])


def get_journals_and_no_issns_from_wtcox(wtcox_tsv_path: Path,
                                         journals_to_ignore: Set[Title],
                                         special_cases: Iterable[Title]) \
        -> (Dict[ISSN, Title], Set[Title], Dict[ISSN, Title]):
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
    :param journals_to_ignore: a set of journal publishers known to not have usage, either because they provide
        access by password only, which doesn't work for us, or they just don't have reports
    :param special_cases: an iterable of journal publishers that have usage but that usage is weird, so we do it
        separately
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


def add_journals_awaiting_fulfillment(journals_awaiting_fulfillment: Dict[ISSN, Title],
                                      from_wtcox: Dict[ISSN, Title])\
        -> Dict[ISSN, Title]:
    """
    Fill in journals missing from report from WTCox.

    To filter out 'Cancelled' journals, we only get 'Fulfilled' subscriptions from WTCox.
    This also, however, filters out 'Awaiting Fulfillment', which should be a vanishingly small
    number of journals depending on when this is run. But you must remember to check for them
    and manually pass a dict indexed by ISSN and containing the name of the journals
    awaiting fulfillment to make sure we have as whole a view as possible.

    As to why .update() isn't just called, mutating global or semi-global objects makes me feel icky,
    so we create a new dict that is a combination of the dict from the WTCox report and the unpacked values
    (search kwargs if unfamiliar with the ** syntax) of the awaiting fulfillment journals.

    :param journals_awaiting_fulfillment: ISSN-indexed dict of titles awaiting fulfillment
    :param from_wtcox: The generated dict from WTCox
    :return: A dict that includes both fulfilled and awaiting fulfillment journals
    """
    return dict(from_wtcox, **journals_awaiting_fulfillment)


def get_usage_stats_from_wtcox_journals(journals_from_wtcox: Dict[ISSN, Title],
                                        path_to_usage_reports: Path)\
        -> UsageReport:
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


def fill_in_missing_dates(usage: UsageReport, dates: Iterable[Month]) -> UsageReport:
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


def fill_in_missing_journals(from_wtcox: Dict[ISSN, Title],
                             usage: UsageReport,
                             dates: Iterable[Month])\
        -> (UsageReport, List[AnyStr]):
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


def write_usage_to_file(usage: UsageReport):
    """Write each journal's usage to a file for upload to LibInsight."""
    for title, use in usage.items():
        with open(os.path.join('data', 'output', title + '.csv'), 'w', encoding='UTF-8', newline='') as w:
            writer = csv.writer(w)
            writer.writerow(('Date', 'Downloads', 'Searches', 'Sessions', 'Views', 'Clicks'))
            for month in sorted(use):
                writer.writerow((month.strftime('%Y-%m-%d'), use[month], 0, 0, 0, 0))


def write_journals_not_found_to_file(not_found: Iterable[Title]):
    """Keep track of the journals we couldn't find any usage for for sanity checks."""
    with open('journals_with_automated_zero_usage.tsv', 'w', encoding='utf-8', newline='') as w:
        writer = csv.writer(w, delimiter='\t')
        for journal in not_found:
            writer.writerow(journal)


def write_journals_with_no_counter_to_file(no_counter: Dict[ISSN, Title]):
    """Keep track of journals that have zero usage because they don't have usage reports or are password-only."""
    with open('no_usage_reports_or_password_only.tsv', 'w', encoding='utf-8', newline='') as w:
        writer = csv.writer(w, delimiter='\t')
        writer.writerow(('Publisher', 'Title'))
        for publisher, title in no_counter.items():
            writer.writerow((publisher, title))


def write_journals_with_no_issn_to_file(no_issns: Iterable[Title]):
    with open('journals_with_no_issn.tsv', 'w', encoding='utf-8', newline='') as w:
        writer = csv.writer(w, delimiter='\t')
        for title in no_issns:
            writer.writerow((title,))


def journals_with_usage_under_threshhold(usage_report: UsageReport, threshold: int) -> List[Title]:
    return [title for title, use in usage_report.items() if sum(use.values()) < threshold]


if __name__ == '__main__':
    no_counter = {'American Association for State & Local History', 'American Association of School Administrators',
                  'American Ceramic Society', 'American Federation of Teachers, AFL-CIO', 'American Library Association',
                  'Artforum International', 'Association for Supervision & Curriculum Development',
                  'Botanical Society of America', 'College Art Association of America', 'Coyne & Blanchard Inc.',
                  'Current History', 'Foreign Policy', 'Harpers Magazine Foundation', 'Harvard Business School',
                  'Harvard Health Publications', 'Institute for Social & Cultural Communications',
                  'International Association of Chiefs of Police', 'Mansueto Ventures LLC', 'Media Source Inc',
                  'National Association of Elementary School Principals', 'National Recreation & Park Association',
                  'New Republic', 'New York State Society of Certified Public Accountants', 'Newbay Media LLC',
                  'North American Society for Sport History', 'Penton Aviation Week Intelligence Network',
                  'Sagamore Publishing LLS', 'Scriptorium Press, Inc.', 'The American Institute for Social Justice',
                  'The Instrumentalist Publishing Company', 'The Society for History Education, Inc.',
                  'Times Supplement LTD', 'ACTE Publications', 'Against the Grain', 'National Council of Teachers of English (NCTE)'}

    special_cases = {'Edizioni Minerva Medica', 'Chronicle of Higher Education', 'Philosophy Documentation Center'}

    dates = [datetime.date(year, month, 1) for month in range(1, 13) for year in range(2015, 2017)]
    dates.extend(datetime.date(2017, month, 1) for month in range(1, 10))

    wtcox_journals, journals_with_no_issn, ignored = get_journals_and_no_issns_from_wtcox(
        os.path.join('data', 'wtcox_no_header_fulfilled.txt'),
        no_counter,
        special_cases)
    wtcox_journals = add_journals_awaiting_fulfillment({'0013-9157': 'Environment'}, wtcox_journals)
    # wtcox_journals['0013-9157'] = 'Environment'  # Environment is currently 'Awaiting fulfillment' and not in report
    usage = get_usage_stats_from_wtcox_journals(wtcox_journals, os.path.join('data', '*.tsv'))
    usage = fill_in_missing_dates(usage, dates)
    usage, not_found = fill_in_missing_journals(wtcox_journals, usage, dates)
    write_usage_to_file(usage)
    write_journals_not_found_to_file(not_found)
    write_journals_with_no_counter_to_file(ignored)
    write_journals_with_no_issn_to_file(journals_with_no_issn)
    print("Not found: " + str(len(not_found)))
    print(str(len(not_found)) + '/' + str(len(usage)))
    print(len(journals_with_usage_under_threshhold(usage, 1)) - len(no_counter))
    assert len(set(wtcox_journals.values())) == len(usage)
