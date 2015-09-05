#!/usr/bin/env python2

from __future__ import print_function

'''
TODO: add threading for web.get

from threading import Thread
a = [None, None]
def fill_pos(idx, val):
    a[idx] = val
threads = [Thread(target=fill_pos, args=(i, '{}{}'.format(i,i))) for i in range(2)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
'''

import unicodedata
import sys
import bs4
import string
import re
import workflow
import workflow.web
import urllib
import argparse
import subprocess
import os
import logging

logging.basicConfig(
    level=logging.DEBUG, 
    filename='/tmp/alfred-nv.log', 
    format='%(asctime)s %(message)s')

assert sys.version_info.major == 2

DEFINITION_URL_TEMPLATE = 'http://m.endic.naver.com/search.nhn?searchOption=all&query={}'
SUGGESTION_URL_TEMPLATE = 'http://ac.endic.naver.com/ac?q={}&q_enc=utf-8&st=1100&r_format=json&r_enc=utf-8&r_lt=1000&r_unicode=0&r_escape=1'

def contains_english(s):
    for letter in string.ascii_letters:
        if letter in s:
            return True
    return False

def strip_hanja_and_numbers(s):
    return ''.join(char for char in s if not is_hanja_or_number(char)).strip()
    
def is_hanja_or_number(char):
    unicode_pos = ord(char)
    if 0x3400 <= unicode_pos < 0xa000:
        return True
    if ord('0') <= unicode_pos <= ord('9'):
        return True
    return False


def process_item(title, subtext=u'', wf=None, url=None):
    # title and subtext should be unicode.
    '''if plaintext, print in brackets.  otherwise, use `wf.add_item`.'''
    if wf is None:
        print(u'[{}] [{}]'.format(title, subtext))
    else:
        wf.add_item(title, subtext, 
            valid=True,
            uid='{:4}'.format(process_item.cur_id),
            autocomplete=title,
            arg=url)
        process_item.cur_id += 1
process_item.cur_id = 0


def process_query(query, wf=None):
    query = unicode(query, encoding='utf-8')
    
    query = unicodedata.normalize('NFC', query) # b/c Alfred sends Korean through as Jamo instead of Hangul
    query = query.encode('utf-8')
    query = urllib.quote(query)
    lookup_definitions(query, wf=wf)
    lookup_suggestions(query, wf=wf)


def lookup_suggestions(query, wf=None):
    url = SUGGESTION_URL_TEMPLATE.format(query)
    r = workflow.web.get(url)
    r.raise_for_status()

    for idx, item_list in enumerate(r.json()['items']):
        for item_pair in item_list:
            possible_query, brief_definition = item_pair[0][0], item_pair[1][0]
            url_to_pass = DEFINITION_URL_TEMPLATE.format(urllib.quote(possible_query.encode('utf-8')))
            process_item('sugg[{}]: '.format(idx) + possible_query, brief_definition, wf=wf, url=url_to_pass)


def lookup_definitions(query, wf=None):
    url = DEFINITION_URL_TEMPLATE.format(query)
    r = workflow.web.get(url)
    r.raise_for_status()

    soup = bs4.BeautifulSoup(r.text, 'html.parser')
    # select the first <ul.li3>, b/c the document has 3: word-idiom, meanings, examples.

    word_idiom_section = soup.select('ul.li3')
    if len(word_idiom_section) == 0:
        process_item("no word-idiom section found. soup: ", soup.prettify(), wf=wf, url=url)
        if wf is not None:
            wf.send_feedback()
        return
    word_idiom_section = word_idiom_section[0]

    sections = word_idiom_section.select('li > dl')
    if len(sections) == 0:
        process_item("no definition sections found. soup: ", word_idiom_section.prettify(), wf=wf, url=url)
        if wf is not None:
            wf.send_feedback()
        return

    for section in sections:

        # title
        assert len(section.select('dt')) == 1
        title_elem = section.select('dt')[0]
        title = title_elem.text.replace('\n', ' ').strip()

        # webcollections are a naver feature that I don't want.
        if 'webCollect' in repr(title_elem):
            process_item(u'#webCollect: {}'.format(title), wf=wf, url=url)
            continue

        # naver gives English->Korean results sometimes.
        # TODO: test our script on english->korean.  Maybe disable this.
        if contains_english(title):
            process_item(u'#contains_english: {}'.format(title), wf=wf, url=url)
            continue
        title = strip_hanja_and_numbers(title)
        process_item(u'title: {}'.format(title), wf=wf, url=url)

        for definition in section.select('dd.tt1 li'):
            definition = re.sub(r'\s+', ' ', definition.text.strip())
            process_item(u'dfn: {}'.format(definition), wf=wf, url=url)

        korean_sentence = section.select('dd.te1')
        if len(korean_sentence) > 1:
            process_item("MULTIPLE KOREAN SENTENCES FOUND. SECTION SOUP: {}".format(section), wf=wf, url=url)
            if wf is not None:
                wf.send_feedback()
            return
        elif len(korean_sentence) == 1:
            korean_sentence = korean_sentence[0].text.replace('\n','').strip()
        
            english_sentence = section.select('dd.tk1')
            if len(english_sentence) != 1:
                process_item("MULTIPLE ENGLISH SENTENCES FOUND. SECTION SOUP: {}".format(section), wf=wf, url=url)
                if wf is not None:
                    wf.send_feedback()
                return
            english_sentence = english_sentence[0].text.replace('\n','').rstrip('play').strip()

            process_item(u'{} = {}'.format(korean_sentence, english_sentence), wf=wf, url=url)


def workflow_main(wf):
    '''
    try:
        process_query(args.query, wf)
    except Exception as exc:
        logging.error('failed main', exc_info=True)
        raise
    '''
    process_query(args.query, wf)
    if wf is not None:
        wf.send_feedback()
    else:
        logging.error('wf should not be None here.')

if __name__ == u'__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plaintext', action='store_true')
    parser.add_argument('query')
    args = parser.parse_args()

    if args.plaintext:
        process_query(args.query)
    else:
        wf = workflow.Workflow()
        log = wf.logger
        sys.exit(wf.run(workflow_main))

