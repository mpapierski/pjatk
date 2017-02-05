# -*- encoding: utf-8 -*-
import click
import requests
import re
import json

from bs4 import BeautifulSoup

re_postback = re.compile(
    r'^javascript:__doPostBack\(\'ctl00\$cphMaster\$OcenyGridView\',\'Page\$(\d+)\'\)$')

message_title = u'Pojawiła się nowa ocena w dziekanacie PJWSTK'


def send_message(title, text, api_key=None, mailgun_domain=None, send_from=None, send_to=None):
    assert api_key is not None
    assert mailgun_domain is not None
    assert send_from is not None
    assert send_to is not None
    click.echo('---')
    click.echo('Send message')
    click.echo(text)
    click.echo('---')
    r = requests.post(
        "https://api.mailgun.net/v3/{}/messages".format(mailgun_domain),
        auth=("api", api_key),
        data={"from": send_from,
              "to": [send_to],
              "subject": title,
              "text": text})
    r.raise_for_status()


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
@click.option('--api-key', required=True)
@click.option('--send-from', required=True)
@click.option('--send-to', required=True)
@click.option('--mailgun-domain', required=True)
def pjatk(login, password, api_key, send_from, send_to, mailgun_domain):
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
        send_message(message_title, message,
                     api_key=api_key, mailgun_domain=mailgun_domain,
                     send_from=send_from, send_to=send_to)
    with open('state.json', 'wb') as f:
        json.dump(oceny, f, indent=4)

    r = s.get('https://dziekanat.pjwstk.edu.pl/Logout.aspx')
    r.raise_for_status()


if __name__ == '__main__':
    pjatk(auto_envvar_prefix='PJATK')
