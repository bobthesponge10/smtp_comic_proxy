import asyncio
import email.parser
import smtplib
from aiosmtpd.controller import Controller
import email, base64, textwrap
import random, asyncio, sys
import os.path as path, os
import tomllib

toml_file_locations = ["config.toml", "/config/config.toml"]

toml_file = None

for i in toml_file_locations:
    if path.isfile(i):
        toml_file = i
        break

if toml_file is None:
    print("No config file found. Exiting")

with open(toml_file, "rb") as f:
    data = tomllib.load(f)

    email_separator = data["email"]["email_separator"]
    email_assigner = data["email"]["email_assigner"]

    external_smtp_host = data["email"]["external_smtp_host"]
    external_smtp_port = data["email"]["external_smtp_port"]
    external_smtp_username = data["email"]["external_smtp_username"]
    external_smtp_password = data["email"]["external_smtp_password"]

    internal_host = data["email"]["internal_host"]
    internal_port = data["email"]["internal_port"]
    internal_size_limit = data["email"]["internal_size_limit"]

    kcc_c2e_path = data["converter"]["kcc_c2e_path"]
    temp_dir = data["converter"]["temp_dir"]
    convertible_files = data["converter"]["convertible_files"]

if not path.isdir(temp_dir):
    os.makedirs(temp_dir)


async def convert_part(part, options):
    filename = part.get_filename()
    if not filename:
        return False
    filetype = filename.split(".")[-1]
    if filetype not in convertible_files:
        return False
    
    attachment_data = part.get_payload(decode=True)
    hash = random.getrandbits(128)
    output_file = '.'.join(filename.split('.')[:-1])+".epub"
    input_filename = path.join(temp_dir, f"{hash}_{filename}")
    output_filename = path.join(temp_dir, f"{hash}_{output_file}")

    try:
        with open(input_filename, "wb") as f:
            f.write(attachment_data)
        
        device = options.get("device", "KV")
        format_ = options.get("format", "EPUB")

        proc = await asyncio.create_subprocess_exec(
            sys.executable, kcc_c2e_path, "-q", "-p", device, "-f", format_, "-u", "-o", output_filename, input_filename,
            stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )

        print("converting")
        stdout, stderr = await proc.communicate()
        if stderr:
            print(stderr)
        print("converted")

        with open(output_filename, "rb") as f:
            new_attachment_data = f.read()
    except Exception as e:
        print(f"error: {e}")
        raise e
    finally:
        if path.exists(input_filename):
            os.remove(input_filename)
        if path.exists(output_filename):
            os.remove(output_filename)
    new_filename = output_file

    part.set_payload(base64.b64encode(new_attachment_data))
    part.replace_header("Content-Type", "")
    part.replace_header("Content-Transfer-Encoding", "")
    part.set_param('application/octet-stream', '')
    part.set_param('name', new_filename)
    part.set_param("base64", "", "Content-Transfer-Encoding")
    part.set_param('filename', new_filename, "Content-Disposition")

    return True

class PassthroughHandler:
    async def handle_DATA(self, server, session, envelope):
        with smtplib.SMTP(host=external_smtp_host, port=external_smtp_port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(external_smtp_username, external_smtp_password)

            input_msg = email.message_from_bytes(envelope.content)
            to_header = [i for i in input_msg._headers if i[0].lower() == "to"][0][1]

            options = {}
            for index in range(len(envelope.rcpt_tos)):
                email_args = envelope.rcpt_tos[index]

                email_parts = email_args.split("|")
                email_ = email_parts[-1]

                envelope.rcpt_tos[index] = email_

                to_header = to_header.replace(email_args, email_)

                for args in email_parts[:-1]:
                    arg, value = args.split(email_assigner, 1)
                    options[arg] = value                

            input_msg.replace_header("To", to_header)

            if input_msg.get_content_maintype() == 'multipart':
                if input_msg.get_content_maintype() == 'multipart':
                    for part in input_msg.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        if part.get('Content-Disposition') is None:
                            continue
                        
                        await convert_part(part, options)

            #smtp.sendmail(envelope.mail_from, envelope.rcpt_tos, input_msg.as_bytes())
            print("forwarded email")


        return '250 Message accepted for delivery'

if __name__ == "__main__":
    controller = Controller(PassthroughHandler(), hostname=internal_host, port=internal_port, data_size_limit=internal_size_limit)
    controller.start()
    asyncio.new_event_loop().run_forever()