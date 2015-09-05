# -*- encoding: utf-8 -*-
import click
import requests
import re
import json
from pushover import init, Client

from bs4 import BeautifulSoup

re_postback = re.compile(
    r'^javascript:__doPostBack\(\'ctl00\$cphMaster\$OcenyGridView\',\'Page\$(\d+)\'\)$')

message_title = u'Pojawiła się nowa ocena w dziekanacie PJWSTK'


def get_form_events(bs):
    events = [
        '__EVENTTARGET',
        '__EVENTARGUMENT',
        '__VIEWSTATE',
        '__EVENTVALIDATION',
        '__VIEWSTATEGENERATOR'
    ]
    event = {}
    for e in events:
        css = 'input#{0}'.format(e)
        l = bs.select(css)
        try:
            event[e] = l[0]['value']
        except IndexError:
            pass

    return event


@click.command()
@click.option('--login', required=True)
@click.option('--password', required=True)
@click.option('--pushover-token', required=True)
@click.option('--pushover-key', required=True)
def pjatk(login, password, pushover_token, pushover_key):
    init(pushover_token)
    pushover = Client(pushover_key, api_token=pushover_token)
    s = requests.Session()
    # Get base values for form
    r = s.get('https://dziekanat.pjwstk.edu.pl/Login.aspx')
    r.raise_for_status()
    bs = BeautifulSoup(r.content, 'html.parser')
    form = get_form_events(bs)
    form['Button1'] = 'Zaloguj'
    form['txtLogin'] = login
    form['txtHaslo'] = password
    # Do actual login
    r = s.post('https://dziekanat.pjwstk.edu.pl/Login.aspx', data=form)
    r.raise_for_status()
    bs = BeautifulSoup(r.content, 'html.parser')
    el = bs.select('span#cphMaster_LabPowitanie font')[0]
    banner = el.text.strip()
    click.echo(banner)
    # Get all marks
    oceny = []
    r = s.get('https://dziekanat.pjwstk.edu.pl/OcenyAll.aspx', data=form)
    r.raise_for_status()
    bs = BeautifulSoup(r.content, 'html.parser')
    grid_view = bs.select('table#cphMaster_OcenyGridView')[0]
    for i, tr in enumerate(grid_view.findAll('tr')):
        if i == 0:
            continue
        tds = tr.select('td')
        if len(tds) == 8:
            values = [td.text.strip() for td in tds]
            d = {}
            (d['przedmiot'],
             d['kod'],
             d['ocena'],
             d['zal_egz'],
             d['ilosc_godzin'],
             d['data'],
             d['prowadzacy'],
             d['semestr']) = values
            oceny.append(d)

    try:
        with open('state.json') as f:
            current_oceny = json.load(f)
    except IOError:
        current_oceny = []

    if oceny != current_oceny:
        message = ''
        for ocena in oceny:
            message += u'{0} {1} {2}\n'.format(ocena['kod'],
                                               ocena['ocena'],
                                               ocena['data'])
        pushover.send_message(message,
                              title=message_title,
                              url='https://dziekanat.pjwstk.edu.pl/Login.aspx')
    with open('state.json', 'wb') as f:
        json.dump(oceny, f, indent=4)

    r = s.get('https://dziekanat.pjwstk.edu.pl/Logout.aspx')
    r.raise_for_status()


if __name__ == '__main__':
    pjatk(auto_envvar_prefix='PJATK')
