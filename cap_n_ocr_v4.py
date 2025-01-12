#start this program with the Switch OS main menu. 
#ACNH should have been running in background with character in front of the house
import time,datetime,calendar
import pytesseract
import traceback
from PIL import Image
import winsound

from signal import signal, SIGINT

from PIL import ImageGrab
import win32gui
import sys, os

import re

import requests 
import json
import base64

import serial
import configparser
import logging

import platform
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import cv2, numpy

from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000

from bgd_cap import cl_bgd_cap

def isSimilarColor(color1, color2):
    THRESHOLD = 10
    # Red Color
    color1_rgb = sRGBColor(color1[0], color1[1], color1[2])

    # Blue Color
    color2_rgb = sRGBColor(color2[0], color2[1], color2[2])

    # Convert from RGB to Lab Color Space
    color1_lab = convert_color(color1_rgb, LabColor)

    # Convert from RGB to Lab Color Space
    color2_lab = convert_color(color2_rgb, LabColor)

    # Find the color difference
    delta_e = delta_e_cie2000(color1_lab, color2_lab)

    return True if delta_e < THRESHOLD else False

def sendMail(to, subject, body = None, attachment_path_list = None):
    msg = MIMEMultipart()

    msg['Subject'] = subject
    msg['From'] = config['GMAIL_NOTIFICATION_USR']
    msg['To'] = to

    msg.attach(MIMEText(body, "plain"))
    
    if attachment_path_list is not None:
        for attachment_path in attachment_path_list:
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
        
            encoders.encode_base64(part)
            filename = attachment_path.split("\\" if platform.uname().system == 'Windows' else '/')[-1]
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {filename}",
            )
            msg.attach(part)

    text = msg.as_string()

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.ehlo()
        server.login(config['GMAIL_NOTIFICATION_USR'], config['GMAIL_NOTIFICATION_PWD'])
        server.sendmail(config['GMAIL_NOTIFICATION_USR'], to.split(','), text)
        server.close()
        
        print ('Email sent!')
    except Exception as x:
        print ('[ERROR] ' + time.ctime() + ': Exception:', x)

def trigger_action(ser,*buttons, sec=0.1):
    if not buttons:
        raise ValueError('No Buttons were given.')
    
    txt = '!'
    for button in buttons:
        # push button
        if button == 'NOTHING':
            time.sleep(sec)
            return
        else:
            txt += str(btnCode[button.upper()]) + ','

    txt = txt[:len(txt)-1] + '@'
    duration = int(sec*40)
    txt += str(duration) + '#'
    ser.write(txt.encode())
    time.sleep(sec - 0.02)

def cchandler(signal_received, frame):
    # Handle any cleanup here
    print('SIGINT or CTRL-C detected. Exiting gracefully')
    #but in this program, press CTRL+C only when we are in the game.
    for action, duration in command_list_g4:
        trigger_action(ser, *action, sec=duration)
    exit(0)
#############################################################################
signal(SIGINT, cchandler)

config_main = configparser.ConfigParser()
config_main.read(os.sep.join([os.path.dirname(os.path.realpath(__file__)),'acnh_config.ini']))
if config_main.has_section('CAP_N_OCR'):
    config = config_main['CAP_N_OCR']
else:
    print('acnh_config.ini not found!!! Exiting...')
    sys.exit(0)

tessdata_dir_config = r'--tessdata-dir "' + config['TESSDATA_DIR'] + r'"'
pytesseract.pytesseract.tesseract_cmd = config['TESSERACT_CMD']

command_list_g1, command_list_g2, command_list_g3, command_list_g4 = [], [], [], []
btnCode = {'L_UP':0,'L_DOWN':1,'L_LEFT':2,'L_RIGHT':3,'R_UP':4,'R_DOWN':5,'R_LEFT':6,'R_RIGHT':7,'X':8,'Y':9,
            'A':10,'B':11,'L':12,'R':13,'THROW':14,'NOTHING':15,'TRIGGERS':16,'HOME':17,'MINUS':18}

bgd_capture = cl_bgd_cap()

thresh = 170
fn = lambda x : 255 if x > thresh else 0

ser = serial.Serial(config['COM_PORT'], 9600, timeout=0,bytesize=8, stopbits=1)
print('<COM port opened. Switching controller...>')
ser.write(b'^') 
time.sleep(20)

rescue_count = 0

while(True):
    #winsound.Beep(2500, 100)

    #Reload config file
    config_main = configparser.ConfigParser()
    config_main.read(os.sep.join([os.path.dirname(os.path.realpath(__file__)),'acnh_config.ini']))
    if config_main.has_section('CAP_N_OCR'):
        config = config_main['CAP_N_OCR']
    else:
        print('acnh_config.ini not found!!! Exiting...')
        sys.exit(0)
    #Reload the command list file so that any changes can be adopted without a restart
    command_list_g1.clear()
    command_list_g2.clear()
    command_list_g3.clear()
    command_list_g4.clear()
    with open(os.sep.join([os.path.dirname(os.path.realpath(__file__)),'command_v4.txt']), 'r') as command_file:
        for command_line in command_file:
            group,action,strDuration = command_line.replace('\n','').split(',')
            actionlist = action.split('&&')
            command_struc = (actionlist,float(strDuration))
            if group == '1':
                command_list_g1.append(command_struc) #from home to price reveal
            elif group == '2':
                command_list_g2.append(command_struc) #from price reveal to saving
            elif group == '3':
                command_list_g3.append(command_struc) #toggle time setting
            elif group == '4':
                command_list_g4.append(command_struc) #release the controller

    homeAttempt = 0
    print(str(time.ctime()), 'Finding home...')
    while True:
        #seek for the frame of the mini map 
        img = bgd_capture.getIM().crop((990,550,993,700))
        pixelcolor1 = img.getpixel((0,0))
        pixelcolor2 = img.getpixel((0,50))
        pixelcolor3 = img.getpixel((0,100))
        pixelcolor4 = img.getpixel((0,149))
        color_ref = (254, 251, 230)
        # print(str(pixelcolor1) + str(isSimilarColor(pixelcolor1,color_ref)))
        # print(str(pixelcolor2) + str(isSimilarColor(pixelcolor2,color_ref)))
        # print(str(pixelcolor3) + str(isSimilarColor(pixelcolor3,color_ref)))
        # print(str(pixelcolor4) + str(isSimilarColor(pixelcolor4,color_ref)))
        
        if not isSimilarColor(pixelcolor1,color_ref) \
            == isSimilarColor(pixelcolor2,color_ref) \
            == isSimilarColor(pixelcolor3,color_ref) \
            == isSimilarColor(pixelcolor4,color_ref) \
            == True:
            trigger_action(ser,'A')
            #This delay is to cope with the latency from the capture card
            time.sleep(1)
            homeAttempt += 1
        else:
            print(str(time.ctime()), 'Mini-map detected! Heading to the shop...')
            for action,duration in command_list_g1:
                trigger_action(ser,*action,sec=duration)
            break
        #Must have bumped into a dialogue with someone
        if homeAttempt >= 200: 
            #something is really wrong (e.g., stuck in conversation to give nickname)
            if rescue_count > 3:
                print(str(time.ctime()), 'Not getting anywhere...exiting...')
                sendMail(config['DEV_MAIL_RECIPIENT'],'Not getting anywhere...exiting...',str(time.ctime()))
                bgd_capture.close()
                sys.exit(0)
            print(str(time.ctime()), 'Unable to get home state! Self rescue triggered...')
            sendMail(config['DEV_MAIL_RECIPIENT'],'Oops... Self rescue triggered...',str(time.ctime()))
            for _ in range(200):
                trigger_action(ser,'B')
                time.sleep(0.25)
            rescue_count += 1

    time.sleep(1)
    iCount = 0
    #seek for dialog background color
    print(str(time.ctime()), 'Start locating the dialog...')
    while True:
        img = bgd_capture.getIM().crop((300,520,620,620))
        #img = ImageGrab.grab(bbox1)
        pixelcolor = img.getpixel((319,0))
        if not isSimilarColor(pixelcolor,(254, 248, 230)):
            print(pixelcolor)
            iCount += 1
            if iCount == 10: 
                print(str(time.ctime()), 'unable to locate the dialog!')
                for _ in range(20):
                    trigger_action(ser,'B')
                    time.sleep(0.25)
                #unable to locate the dialog. Keep the iCount value to skip rest of the loop
            else:
                time.sleep(0.2)
                continue
        else:
            iCount = 0
            img = img.convert('L').point(fn, mode='1')            
            text = pytesseract.image_to_string(img,lang='acnh',config=tessdata_dir_config)
            
            if '当前' in text:
                #To ensure the entire text containing the turnip price is fully displayed
                time.sleep(0.4)
                #img = ImageGrab.grab(bbox1).convert('L').point(fn, mode='1')
                img = bgd_capture.getIM().crop((300,520,620,620)).convert('L').point(fn, mode='1')
                #img.save(os.sep.join([config['CAP_DIR'],'cap_succ_' + str(int(time.time())) + '.jpg']))
                img = img.crop((0,50,320,100))
                filename = os.sep.join([config['CAP_DIR'],'cap_succ_crop_' + str(int(time.time())) + '.jpg'])
                img.save(filename)
                text = re.compile(r'(\r+|\n+|\s+)').sub('',pytesseract.image_to_string(img,lang='acnh',config=tessdata_dir_config))
                #text = pytesseract.image_to_string(img,lang='acnh').replace('\r','').replace('\n','')
                
                #winsound.Beep(2500, 500)                
                strPrice = ''
                for element in text.lstrip():
                    if element.isnumeric():
                        strPrice += element
                    else:
                        break
                print(str(time.ctime()), text, '|', strPrice)
                with open(os.sep.join([config['CAP_DIR'],'cap_price_log.txt']), 'a') as f:
                    f.write(';'.join((str(datetime.datetime.now().strftime(r'%m/%d/%Y')),
                        str(datetime.datetime.now().strftime(r'%H:%M:%S')),
                        str(calendar.timegm((datetime.datetime.now(datetime.timezone.utc)).timetuple())),
                        strPrice)) + '\n')
                rescue_count = 0
                if int(strPrice) >= int(config['PRICE_THRESHOLD']):
                    winsound.Beep(3200, 5000)
                    #pullPlug()

                    attachment_path_list = []
                    attachment_path_list.append(filename)
                    sendMail(config['DEV_MAIL_RECIPIENT'],'Turnip Price@'+strPrice,str(time.ctime()),attachment_path_list)
                    
                    config_temp = configparser.ConfigParser()
                    try:
                        config_temp.read(os.sep.join([os.path.dirname(os.path.realpath(__file__)),'dodoapp_local_config.ini']))
                    except Exception as x:
                        config_temp['DODOApp'] = {}
                    config_temp['DODOApp']['island_price'] = strPrice
                    with open(os.sep.join([os.path.dirname(os.path.realpath(__file__)),'dodoapp_local_config.ini']), 'w') as configfile:
                        config_temp.write(configfile)

                    #finish the conversation
                    for _ in range(15):
                        trigger_action(ser,'B')
                        time.sleep(0.25)
                    time.sleep(2)
                    #walk out of the store
                    trigger_action(ser, 'L_DOWN', sec=2.5)
                    for _ in range(15):
                        trigger_action(ser,'B')
                        time.sleep(0.25)
                    while True:
                        #seek for the frame of the mini map 
                        img = bgd_capture.getIM().crop((990,550,993,700))
                        pixelcolor1 = img.getpixel((0,0))
                        pixelcolor2 = img.getpixel((0,50))
                        pixelcolor3 = img.getpixel((0,100))
                        pixelcolor4 = img.getpixel((0,149))
                        color_ref = (254, 251, 230)
                        # print(str(pixelcolor1) + str(isSimilarColor(pixelcolor1,color_ref)))
                        # print(str(pixelcolor2) + str(isSimilarColor(pixelcolor2,color_ref)))
                        # print(str(pixelcolor3) + str(isSimilarColor(pixelcolor3,color_ref)))
                        # print(str(pixelcolor4) + str(isSimilarColor(pixelcolor4,color_ref)))
                        
                        if not isSimilarColor(pixelcolor1,color_ref) \
                            == isSimilarColor(pixelcolor2,color_ref) \
                            == isSimilarColor(pixelcolor3,color_ref) \
                            == isSimilarColor(pixelcolor4,color_ref) \
                            == True:
                            time.sleep(0.25)
                        else:
                            break
                    trigger_action(ser, 'L_DOWN', sec=0.3)
                    trigger_action(ser, 'L_RIGHT', sec=0.4)
                    trigger_action(ser,'X')
                    time.sleep(2)
                    #reposition cursor to #1 slot in bag
                    trigger_action(ser, 'L_DOWN', sec=2)
                    trigger_action(ser, 'L_LEFT')
                    trigger_action(ser, 'L_UP', sec=2)
                    time.sleep(1)
                    is_cursor_on_van = False
                    for _ in range(4):
                        for _ in range(10):
                            img = bgd_capture.getIM().crop((220, 80, 1030, 530))
                            cv2_img = cv2.cvtColor(numpy.array(img), cv2.COLOR_BGR2GRAY)
                            img_ref = cv2.cvtColor(
                                cv2.imread(os.sep.join([os.path.dirname(os.path.realpath(__file__)),'ref_img','txtVan.jpg'])), cv2.COLOR_BGR2GRAY)
                            res = cv2.matchTemplate(cv2_img, img_ref, cv2.TM_CCOEFF_NORMED)
                            print(res.max())
                            threshold = 0.90
                            loc = numpy.where(res >= threshold)
                            for pt in zip(*loc[::-1]):
                                #deploy van on the ground
                                is_cursor_on_van = True
                                trigger_action(ser,'A')
                                time.sleep(1)
                                trigger_action(ser,'A')
                                break        
                            if is_cursor_on_van:
                                break
                            trigger_action(ser,'L_RIGHT')
                            time.sleep(0.5)
                        if is_cursor_on_van:
                            break
                        trigger_action(ser,'L_DOWN')
                        time.sleep(0.5)

                    time.sleep(2)
                    img = bgd_capture.getIM().crop((50,80,1230,740))
                    #img.save(os.sep.join([config['CAP_DIR'],'cap_succ_' + str(int(time.time())) + '.jpg']))
                    filename = os.sep.join([config['CAP_DIR'],'cap_van_' + str(int(time.time())) + '.jpg'])
                    img.save(filename)
                    
                    # send a screenshot after deploying the van, so that if the position is good,
                    # open_island program can be triggered right after.
                    attachment_path_list = []
                    attachment_path_list.append(filename)
                    sendMail(config['DEV_MAIL_RECIPIENT'],'Van Position Check',str(time.ctime()),attachment_path_list)
                    
                    for _ in range(3):
                        trigger_action(ser,'L_LEFT', sec=1)
                        trigger_action(ser,'L_DOWN', sec=5)    
                    for _ in range(3):
                        trigger_action(ser,'L_LEFT', sec=1)
                        trigger_action(ser,'L_RIGHT', sec=0.2)
                        trigger_action(ser,'L_DOWN', sec=5)    

                    trigger_action(ser,'L_LEFT', sec=3)
                    trigger_action(ser,'L_RIGHT', sec=0.6)
                    trigger_action(ser,'L_UP', sec=0.3)

                    #release the control for other controllers to connect
                    for action,duration in command_list_g4:
                        trigger_action(ser,*action,sec=duration)
                    
                    bgd_capture.close()
                    sys.exit(0)

        for action,duration in command_list_g2:
            trigger_action(ser,*action,sec=duration)

        if iCount == 0: #iCount == 0 means we have gone through the complete conversation
            for action,duration in command_list_g3:
                trigger_action(ser,*action,sec=duration) 
        else:
            sendMail(config['DEV_MAIL_RECIPIENT'],'Oops... Didn\'t make it to the shop.',str(time.ctime()))

        bgd_capture.showWindow()
        break