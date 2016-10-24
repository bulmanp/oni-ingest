#!/bin/env python

import logging
import json
import os
import sys
import copy
from oni.utils import Util, NewFileEvent
from oni.kafka_client import KafkaTopic
from multiprocessing import Pool
from oni.file_collector import FileWatcher
import time

class Collector(object):
    
    def __init__(self,hdfs_app_path,kafka_topic,conf_type):
        
        self._initialize_members(hdfs_app_path,kafka_topic,conf_type)
        
    def _initialize_members(self,hdfs_app_path,kafka_topic,conf_type):
        
        # getting parameters.
        self._logger = logging.getLogger('ONI.INGEST.PROXY')
        self._hdfs_app_path = hdfs_app_path
        self._kafka_se= kafka_topic

        self._kafka_conf = {}
        self._kafka_conf['servers'] = kafka_topic.BootstrapServers
        self._kafka_conf['topic'] = kafka_topic.Topic
        print self._kafka_conf

        # get script path
        self._script_path = os.path.dirname(os.path.abspath(__file__))

        # read proxy configuration.
        conf_file = "{0}/ingest_conf.json".format(os.path.dirname(os.path.dirname(self._script_path)))
        conf = json.loads(open(conf_file).read())
        self._message_size = conf["kafka"]["message_size"]
        self._conf = conf["pipelines"][conf_type]

        # get collector path.
        self._collector_path = self._conf['collector_path']

        #get supported files
        self._supported_files = self._conf['supported_files']

        # create collector watcher
        self._watcher = FileWatcher(self._collector_path,self._supported_files)

        # Multiprocessing. 
        self._processes = 5
        self._ingestion_interval = 5
        self._pool = Pool(processes=self._processes)

    def start(self):

        self._logger.info("Starting PROXY INGEST")
        self._watcher.start()   
    
        try:
            while True:
                #self._ingest_files()
                self._ingest_files_pool()              
                time.sleep(self._ingestion_interval)
        except KeyboardInterrupt:
            self._logger.info("Stopping Proxy collector...")  
            Util.remove_kafka_topic(self._kafka_topic.Zookeeper,self._kafka_topic.Topic,self._logger)          
            self._watcher.stop()
            self._pool.terminate()
            self._pool.close()            
            self._pool.join()
             

    def _ingest_files_pool(self,):
            
       
        if self._watcher.HasFiles:
            
            for x in range(0,self._processes):
                file = self._watcher.GetNextFile()
                resutl = self._pool.apply_async(ingest_file,args=(file,self._message_size,self._kafka_topic.Topic,self._kafka_topic.BootstrapServers))
                #resutl.get() # to debug add try and catch.
                if  not self._watcher.HasFiles: break    
        return True


def ingest_file(file,message_size,topic,kafka_servers):
    
    logger = logging.getLogger('ONI.INGEST.PROXY.{0}'.format(os.getpid()))
    try:        
        message = ""
        logger.info("Ingesting file: {0} process:{1}".format(file,os.getpid())) 
        with open(file,"rb") as f:
            for line in f:
                message += line
                if len(message) > message_size:
                    KafkaTopic.SendMessage(message,kafka_servers,topic,0)
                    message = ""
            #send the last package.
            print kafka_servers
            KafkaTopic.SendMessage(message,kafka_servers,topic,0)
            #U.send_message(message,self._kafka_topic.Partition,log_message=False)
        rm_file = "rm {0}".format(file)
        Util.execute_cmd(rm_file,logger)
        #logger.info("File {0} has been successfully sent to Kafka Topic:{1}".format(file,self._kafka_topic.Topic))
        logger.info("File {0} has been successfully sent to Kafka Topic:".format(file))

    except Exception as err:
        logger.error("There was a problem, please check the following error message:{0}".format(err.message))
