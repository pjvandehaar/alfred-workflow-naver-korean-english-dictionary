#!/usr/bin/env python2
# -*- coding: utf-8 -*-

'''
PROBLEMS:
- on <http://m.endic.naver.com/search.nhn?searchOption=all&query=cat>, the title "cat2" comes through from a `<sup>2</sup>`.
'''


from __future__ import print_function

import threading
import traceback
import unicodedata
import sys
import bs4
import re
import workflow
import workflow.web
import urllib
import argparse
import logging

logging.basicConfig(
    level=logging.DEBUG,
    filename='/tmp/alfred-nv.log',
    format='%(asctime)s %(message)s')

assert sys.version_info.major == 2

DEFINITION_URL_TEMPLATE = 'http://m.endic.naver.com/search.nhn?searchOption=all&query={}'
SUGGESTION_URL_TEMPLATE = 'http://ac.endic.naver.com/ac?q={}&q_enc=utf-8&st=1100&r_format=json&r_enc=utf-8&r_lt=1000&r_unicode=0&r_escape=1'

def fetch_definition_and_suggestion_page_contents(query):
    rv = [None, None]
    urls = list(template.format(query) for template in [DEFINITION_URL_TEMPLATE, SUGGESTION_URL_TEMPLATE])
    def fetch_url_by_idx(idx):
        rv[idx] = workflow.web.get(urls[idx])
        rv[idx].raise_for_status()

    threads = [threading.Thread(target=fetch_url_by_idx, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return rv

def clean_text(s):
    for bad_letter in '\n\r\t':
        s = s.replace(bad_letter, ' ')
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def process_item(title, subtext=u'', url=None, autocomplete=None):
    '''
    If plaintext, print.  else, use `wf.add_item`.
    `title` and `subtext` should be unicode.
    '''

    if process_item.wf is None:
        print(u' {:15}      {}'.format(title, subtext).encode('utf-8'))
    else:
        kwargs = {'copytext':title}

        if autocomplete is None:
            kwargs['autocomplete'] = title
        else:
            kwargs['autocomplete'] = autocomplete

        if url is not None:
            kwargs['arg'], kwargs['valid'] = url, True
        elif process_item.default_url is not None:
            kwargs['arg'], kwargs['valid'] = process_item.default_url, True

        process_item.wf.add_item(title, subtext, **kwargs)
process_item.wf = None
process_item.default_url = None


def lookup_suggestions(response):

    num_entries = 0
    for idx, item_list in enumerate(response.json()['items']):
        for item_pair in item_list:
            possible_query, brief_definition = item_pair[0][0], item_pair[1][0]
            url_to_pass = DEFINITION_URL_TEMPLATE.format(urllib.quote(possible_query.encode('utf-8')))
            process_item('sugg[{}]: '.format(idx) + possible_query,
                         brief_definition,
                         url=url_to_pass,
                         autocomplete=possible_query)
            num_entries += 1

    return num_entries


def lookup_definitions(response):

    soup = bs4.BeautifulSoup(response.text, 'html.parser')

    # Hopefully these are exactly the <div>s that we want.
    divs = soup.select('div#content div.entry_wrap div.section_card div.entry_search_word')

    for div in divs:

        title_text = None
        definition_texts = []
        example_texts = []

        title = div.select('a.h_word')
        if len(title) != 1:
            raise Exception('no title for {}'.format(repr(title)))
        else:
            title = title[0]
            title_text = clean_text(title.text)

        single_dfn = div.select('p.desc_lst')
        if len(single_dfn) > 1:
            raise Exception('multiple single definitions!')
        elif len(single_dfn) == 1:
            single_dfn = single_dfn[0]
            dfn_text = single_dfn.text
            definition_texts.append(clean_text(dfn_text))

        dfns = div.select('ul.desc_lst li')
        for dfn in dfns:
            p_descs = dfn.select('p.desc')
            if len(p_descs) == 0:
                # must be a web collection
                dfn_text = dfn.text
            elif len(p_descs) == 1:
                dfn_text = p_descs[0].text
            else:
                raise Exception('there are {} `p.desc`s in {}'.format(len(p_descs), repr(dfn)))
            definition_texts.append(clean_text(dfn_text))

        examples = div.select('div.example_wrap')
        for example in examples:
            kor = example.select('p.example_mean')[0].text

            # this is to avoid the pesky "Play" or "발음듣기" at the end of the line.
            eng_spans = example.select('p.example_stc span.autolink')
            eng = ' '.join(span.text for span in eng_spans)

            example_text = kor  +' = ' + eng
            example_texts.append(clean_text(example_text))

        # make some output!
        if len(example_texts) <=1 and sum(len(dfn_text) for dfn_text in definition_texts) <= 40:
            # we'll concatenate some definitions together to qualify for a one-liner.
            definition_texts = [' || '.join(dfn_text for dfn_text in definition_texts)]

        if len(definition_texts) <= 1 and len(example_texts) <= 1:
            # make a one-liner.
            d_text = '' if len(definition_texts) ==0 else definition_texts[0]
            e_text = '' if len(example_texts) ==0 else example_texts[0]
            process_item(u'{} = {}'.format(title_text, d_text), e_text)

        else:
            # print a title line followed by everything else.
            process_item(u'== {} =='.format(title_text))
            for definition_text in definition_texts:
                process_item(u'    ' + definition_text)
            for example_text in example_texts:
                process_item(u'    ' + example_text)


    return len(divs)


def process_query(query):
    query = unicode(query, encoding='utf-8')
    query = unicodedata.normalize('NFC', query) # b/c Alfred sends Korean through as Jamo instead of Hangul
    query = query.encode('utf-8')
    query = urllib.quote(query)

    process_item.default_url = DEFINITION_URL_TEMPLATE.format(query)

    dfns_response, sugg_response = fetch_definition_and_suggestion_page_contents(query)

    n_dfns = lookup_definitions(dfns_response)
    n_sugg = lookup_suggestions(sugg_response)
    if n_dfns + n_sugg == 0:
        process_item('no results found')


def workflow_main(wf):
    '''wrapper around `process_query` for use by alfred, or just printing xml.'''
    process_item.wf = wf

    try:
        process_query(args.query)
    except Exception as exc:
        logging.error('failed main', exc_info=True)

        process_item('EXCEPTION OCCURRED', repr(exc.args))
        tb = traceback.format_exc()
        for line in tb.split('\n'):
            process_item('traceback:' + line)
    wf.send_feedback()

if __name__ == u'__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plaintext', action='store_true')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('query', nargs='?', default=None)
    args = parser.parse_args()

    if not args.test and args.query is None:
        parser.print_help()
        exit(1)

    if args.test:
        tests = ['강', '조언', '뭘 해야 할까요', '그리기에', '집중할', 'cat', 'I am a potato']
        for test in tests:
            print('TESTING WITH:', test)
            process_query(test)
            print('')
    elif args.plaintext:
        process_query(args.query)
    else:
        wf = workflow.Workflow()
        log = wf.logger
        sys.exit(wf.run(workflow_main))
