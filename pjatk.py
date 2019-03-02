# -*- encoding: utf-8 -*-
import click
import requests
import re
import json
import sys
import operator
from jinja2 import Template
from datetime import datetime
import pickle
from bs4 import BeautifulSoup

re_postback = re.compile(
    r'^javascript:__doPostBack\(\'ctl00\$cphMaster\$OcenyGridView\',\'Page\$(\d+)\'\)$')

message_title = u'Pojawiła się nowa ocena w dziekanacie PJWSTK'


def send_message(title, text, api_key=None, mailgun_domain=None, send_from=None, send_to=None, html=None):
    assert api_key is not None
    assert mailgun_domain is not None
    assert send_from is not None
    assert send_to is not None
    click.echo('---')
    click.echo('Send message')
    click.echo(text)
    click.echo('---')
    data = {"from": send_from,
            "to": [send_to],
            "subject": title,
            "text": text}
    if html is not None:
        data['html'] = html
    r = requests.post(
        "https://api.mailgun.net/v3/{}/messages".format(mailgun_domain),
        auth=("api", api_key),
        data=data)
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

@click.group()
def cli():
    pass

@click.command()
@click.option('--login', required=True)
@click.option('--password', required=True)
@click.option('--api-key', required=True)
@click.option('--send-from', required=True)
@click.option('--send-to', required=True)
@click.option('--mailgun-domain', required=True)
def oceny(login, password, api_key, send_from, send_to, mailgun_domain):
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
    try:
        el = bs.select('span#cphMaster_LabPowitanie font')[0]
    except Exception as e:
        try:
            body = bs.select('body')[0]
            lines = list(line.strip() for line in body.text.splitlines() if line.strip())
            for line in lines:
                click.echo(line)
            sys.exit(1)
        except Exception as e:
            click.echo('Totally unexpected error')
            with open('error.html', 'wb') as fout:
                fout.write(r.content)
                raise
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


@click.command()
@click.option('--login', required=True)
@click.option('--password', required=True)
@click.option('--api-key', required=True)
@click.option('--send-from', required=True)
@click.option('--send-to', required=True)
@click.option('--mailgun-domain', required=True)
def podania(login, password, api_key, send_from, send_to, mailgun_domain):
    s = requests.Session()
    # Get base values for form
    r = s.get('https://podania.pjwstk.edu.pl/login.aspx')
    r.raise_for_status()
    bs = BeautifulSoup(r.content, 'html.parser')
    form = get_form_events(bs)
    form['__EVENTTARGET'] = ''
    form['__EVENTARGUMENT'] = ''
    form['Button1'] = 'Zaloguj'
    form['TextBox1'] = login
    form['TextBox2'] = password
    r = s.post('https://podania.pjwstk.edu.pl/login.aspx', data=form)
    r.raise_for_status()
    bs = BeautifulSoup(r.content, 'html.parser')
    hello = bs.select("#ContentPlaceHolder1_Label1")[0]
    print(hello.text)

    r = s.get('https://podania.pjwstk.edu.pl/wyslane.aspx')
    r.raise_for_status()
    bs = BeautifulSoup(r.content, 'html.parser')
    table = bs.select("#ContentPlaceHolder1_GridView2")[0]

    podania = []

    for row in table.select("tr"):
        cols = list(row.select("td"))
        if not cols:
            continue
        student = cols[0].text.strip()
        url = cols[0].select("a")[0]['href']
        wys, = re.search(r'^podanie\.aspx\?wys=(\d+)$', url).groups()
        wys = int(wys)
        typ_podania = cols[1].text.strip()
        status = cols[2].text.strip()
        data_zlozenia = cols[3].text.strip()
        data_zlozenia = datetime.strptime(data_zlozenia, '%d.%m.%Y %H:%M:%S')
        r = s.get('https://podania.pjwstk.edu.pl/{}'.format(url))
        r.raise_for_status()
        bs = BeautifulSoup(r.content, 'html.parser')
        # Get details
        wnioskodawca = bs.select('#ContentPlaceHolder1_lblStud')[0]
        for br in wnioskodawca.find_all("br"):
            br.replace_with("\n")
        wnioskodawca = wnioskodawca.text.strip()
        uzasadnienie = bs.select('#ContentPlaceHolder1_uzasad')[0].text.strip()

        historia = []

        for i, row_historia in enumerate(bs.select('#ContentPlaceHolder1_GridView1')[0].select("tr")):
            cols = list(row_historia.select("td"))
            if not cols:
                continue
            miejsce_podania = cols[0].text.strip()
            data = cols[1].text.strip()
            status = cols[2].text.strip()
            informacja = cols[3].text.strip()
            
            data = {
                'miejsce_podania': miejsce_podania,
                'data': datetime.strptime(data, '%d.%m.%Y %H:%M:%S') if data else None,
                'status': status,
                'informacja': informacja,
            }
            historia.append(data)

        podania.append({
            'student': student,
            'url': url,
            'wys': wys,
            'typ_podania': typ_podania,
            'data_zlozenia': data_zlozenia,
            'wnioskodawca': wnioskodawca,
            'historia': historia,  
            'uzasadnienie': uzasadnienie,
        })

    podania.sort(key=operator.itemgetter('data_zlozenia'), reverse=True)


    def default(o):
        if isinstance(o, (datetime,)):
            return o.isoformat()

    with open('podania.json', 'w') as podania_json:
        json.dump(podania, podania_json, sort_keys=True, indent=4, default=default)
    
    try:
        with open('podania_state.pickle', 'rb') as podania_pickle:
            # pickle because it contains datetime objects
            current_podania = pickle.load(podania_pickle)
    except IOError:
        current_podania = []
    if podania != current_podania:
        with open('podania.html') as tpl:
            template = Template(tpl.read())
            content = template.render(podania=podania)
            print('Sending email...')
            send_message('Zmiany w systemie podań', json.dumps(podania, sort_keys=True, indent=4, default=default),
                     api_key=api_key, mailgun_domain=mailgun_domain,
                     send_from=send_from, send_to=send_to, html=content)

        with open('podania_state.pickle', 'wb') as podania_pickle:
            pickle.dump(podania, podania_pickle)

    r = s.get('https://podania.pjwstk.edu.pl/logout.aspx')
    r.raise_for_status()


cli.add_command(podania)
cli.add_command(oceny)
if __name__ == '__main__':
    cli(auto_envvar_prefix='PJATK')