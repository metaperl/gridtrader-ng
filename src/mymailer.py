import logging

logging.basicConfig(level=logging.DEBUG)

def _send_via_gmail(user, password, recipient, subject, body):
    import smtplib

    gmail_user = user
    gmail_pwd = password
    FROM = user
    TO = recipient if type(recipient) is list else [recipient]
    SUBJECT = subject
    TEXT = body

    # Prepare actual message
    message = """From: %s\nTo: %s\nSubject: %s\n\n%s
    """ % (FROM, ", ".join(TO), SUBJECT, TEXT)
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo()
        server.starttls()
        server.login(gmail_user, gmail_pwd)
        server.sendmail(FROM, TO, message)
        server.close()
        logging.debug('successfully sent the mail')
    except Exception as e:
        logging.debug('failed to send mail %s', e)


def send_via_email(account, body):
    _send_via_gmail(
        'terrence.brannon@gmail.com',
        'serca972Yancey!',
        'terrence.brannon@gmail.com',
        '({}) ADSactly Grid Trader Error'.format(account),
        body
    )

def send_email(grid_trader, error_msg):

    # Import smtplib for the actual sending function
    import smtplib

    # Import the email modules we'll need
    from email.mime.text import MIMEText

    msg = MIMEText(error_msg)

    # me == the sender's email address
    # you == the recipient's email address
    msg['Subject'] = '({}) Error has occured'.format(grid_trader.account)
    msg['From'] = me = 'gridtrader@arbit.ca'
    msg['To'] = you = grid_trader.config.get('admin', 'email')

    # Send the message via our own SMTP server, but don't include the
    # envelope header.
    s = smtplib.SMTP(grid_trader.config.get('admin', 'smtpServer'))
    s.sendmail(me, [you], msg.as_string())
    s.quit()
