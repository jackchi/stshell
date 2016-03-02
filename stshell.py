#!/usr/bin/env python
#
# Copyright 2016 Henric Andersson
#
# The base for a shell like interface to your smartthings account,
# allowing the following:
#
# - Create SA/DTH
# - Upload of individual files to SA/DTH
# - Download of individual files and complete SA/DTH
# - Delete of individual files or complete SA/DTH
#

import requests
import json
import re
import os
import sys

class STServer:
    TYPE_SA = 1
    TYPE_DTH = 2

    UPLOAD_OTHER = 'OTHER'
    UPLOAD_IMAGE = 'IMAGE'
    UPLOAD_CSS = 'CSS'
    UPLOAD_I18N = 'I18N'
    UPLOAD_JAVASCRIPT = 'JAVASCRIPT'
    UPLOAD_VIEW = 'VIEW'

    URL_PATH = {}
    URL_PATH['login'] = '/j_spring_security_check'
    URL_PATH['smartapps'] = '/ide/apps'
    URL_PATH['smartapp-resources'] = '/ide/app/getResourceList'
    URL_PATH['smartapp-download'] = '/ide/app/getCodeForResource'
    URL_PATH['smartapp-create'] = '/ide/app/saveFromCode'
    URL_PATH['smartapp-upload'] = '/ide/app/uploadResources'
    URL_PATH['smartapp-editor'] = '/ide/app/editor/'
    URL_PATH['smartapp-delete'] = '/ide/app/deleteResource'
    URL_PATH['smartapp-destroy'] = '/ide/app/delete/'

    URL_PATH['devicetypes'] = '/ide/devices'
    URL_PATH['devicetype-resources'] = '/ide/device/getResourceList'
    URL_PATH['devicetype-download'] = '/ide/device/getCodeForResource'
    URL_PATH['devicetype-upload'] = '/ide/device/uploadResources'
    URL_PATH['devicetype-editor'] = '/ide/device/editor/'
    URL_PATH['devicetype-delete'] = '/ide/device/deleteResource'
    URL_PATH['devicetype-create'] = '/ide/device/saveFromCode'
    URL_PATH['devicetype-destroy'] = '/ide/device/update'

    def __init__(self, username, password, baseUrl):
        self.URL_BASE = baseUrl
        self.USERNAME = username
        self.PASSWORD = password
        self.session = requests.Session()

    def resolve(self, type=None):
        if type is None:
            return self.URL_BASE
        return "%s/%s" % (self.URL_BASE, self.URL_PATH[type])

    def login(self):
        post = {"j_username" : self.USERNAME, "j_password" : self.PASSWORD}
        r = self.session.post(self.resolve("login"), data=post, cookies={})
        if r.status_code == 200 and "JSESSIONID" in self.session.cookies.keys():
            return True
        print "ERROR: Failed to login"
        return False

    def listSmartApps(self):
        """
        " Returns a hashmap with the ID of the app as key and the name and namespace
        """
        r = self.session.post(self.resolve("smartapps"))
        if r.status_code != 200:
            print "ERROR: Failed to get smartapps list"
            return None

        apps = re.compile('\<a href="/ide/app/editor/([^"]+)".*?\>\<img .+?\>\s*(.+?)\s*:\s*(.+?)\</a\>', re.MULTILINE|re.IGNORECASE|re.DOTALL)
        lst = apps.findall(r.text)

        result = {}
        if lst is not None:
            for i in lst:
                result[i[0]] = {'id' : i[0], 'namespace' : i[1], 'name' : i[2]}
        return result

    def listDeviceTypes(self):
        """
        " Returns a hashmap with the ID of the app as key and the name and namespace
        """
        r = self.session.post(self.resolve("devicetypes"))
        if r.status_code != 200:
            print "ERROR: Failed to get smartapps list"
            return None

        apps = re.compile('\<a href="/ide/device/editor/([^"]+)".*?\>\s*(.+?)\s*:\s*(.+?)\</a\>', re.MULTILINE|re.IGNORECASE|re.DOTALL)
        lst = apps.findall(r.text)

        result = {}
        if lst is not None:
            for i in lst:
                result[i[0]] = {'id' : i[0], 'namespace' : i[1], 'name' : i[2]}
        return result

    def __lister__(self, details, lst):
        for d in details:
            if "id" in d.keys():
                lst.append(d["id"])
            elif "children" in d.keys():
                lst = self.__lister__(d["children"], lst)
        return lst

    def getFileDetails(self, path, uuid):
        """ Returns a list of files contained in this smartapp """
        r = self.session.post(self.resolve(path), params={"id" : uuid})
        if r.status_code != 200:
            return None

        lst = self.__lister__(r.json(), [])

        return {"details" : r.json(), "flat" : lst }

    def getSmartAppDetails(self, smartapp):
        """ Returns a list of files contained in this smartapp """
        return self.getFileDetails("smartapp-resources", smartapp)

    def getDeviceTypeDetails(self, devicetype):
        """ Returns a list of files contained in this devicetype """
        return self.getFileDetails("devicetype-resources", devicetype)

    def __digger__(self, details, uuid, path):
        result = None
        for d in details:
            if "id" in d.keys() and d["id"] == uuid:
                return {"filename" : d["text"], "type" : d["li_attr"]["resource-type"], "content" : d["li_attr"]["resource-content-type"], "path" : path}
            elif "children" in d.keys():
                result = self.__digger__(d["children"], uuid, path + "/" + d["text"])

            if result is not None:
                break

        return result

    def getDetail(self, details, uuid):
        """ Builds a path and extracts the necessary parts to successfully download an item """
        info = self.__digger__(details, uuid, "")
        return info

    def downloadItem(self, path, owner, details, uuid):
        """ Downloads the selected item and returns it """
        details = self.getDetail(details, uuid)
        if details is None:
            print "ERROR: Unable to get details of item"
            return None

        r = self.session.post(self.resolve(path), params={"id" : owner, "resourceId" : uuid, "resourceType" : details["type"]})
        if r.status_code != 200:
            print "ERROR: Unable to download item"
            return None

        details["data"] = r.content
        return details

    def createSmartApp(self, content):
        payload = {"fromCodeType" : "code", "create" : "Create", "content" : content}
        r = self.session.post(self.resolve("smartapp-create"), data=payload, allow_redirects=False)
        if r.status_code != 302:
            print "ERROR: Unable to create item"
            return None

        p = re.compile('.*/ide/app/editor/([a-f0-9\-]+)', re.MULTILINE|re.IGNORECASE|re.DOTALL)
        m = p.match(r.headers["Location"])

        return m.group(1)

    def deleteSmartApp(self, uuid):
        r = self.session.get(self.resolve("smartapp-destroy") + uuid, allow_redirects=False)
        if r.status_code == 302:
            return True
        return False

    def getSmartAppIds(self, uuid):
        r = self.session.get(self.resolve("smartapp-editor") + uuid)
        """
        ST.AppIDE.init({
                            url: '/ide/app/',
                            websocket: 'wss://ic.connect.smartthings.com:8443/',
                            client: '1af9e4e7-9a2d-47a4-9edf-c9f326642489',
                            id: '19d2016d-2337-46bc-ae0e-143e033d4a63',
                            versionId: '5d01fb38-cd7f-48b3-be2f-2509efb09020',
                            state: 'NOT_APPROVED'
                        });
        """

        p = re.compile('ST\.AppIDE\.init\(\{.+?url: \'([^\']+)\',.+?websocket: \'([^\']+)\',.+?client: \'([^\']+)\',.+?id: \'([^\']+)\',.+?versionId: \'([^\']+)\',.+?state: \'([^\']+)\'', re.MULTILINE|re.IGNORECASE|re.DOTALL)
        m = p.search(r.text)

        if m:
            return {
                "url" : m.group(1),
                "websocket" : m.group(2),
                "client" : m.group(3),
                "id" : m.group(4),
                "versionid" : m.group(5),
                "state" : m.group(6)
            }
        return None

    """ Uploads content to server, needs special uuid which is not same as app uuid """
    def uploadSmartAppItem(self, uuid, content, filename, path, kind):
        files = {"fileData" : (filename, content)}
        data = {
            "id" : uuid,
            "file-type|" + filename : kind,
            "file-path|" + filename : path,
            "uploadResource" : "Upload"
        }

        r = self.session.post(self.resolve("smartapp-upload"), data=data, files=files)
        if r.status_code == 200:
            return True
        return False

    def deleteSmartAppItem(self, uuid, item):
        r = self.session.post(self.resolve('smartapp-delete'), data={"id" : uuid, "resourceId" : item})
        if r.status_code == 200:
            return True
        return False

    def getDeviceTypeIds(self, uuid):
        """
            var codeModified = false;
            $(function() {
                ST.DeviceIDE.init({
                    url: '/ide/device/',
                    websocket: 'wss://ic.connect.smartthings.com:8443/',
                    client: '3f69d079-6b7a-427c-82ea-a7ed718ca7f8',
                    id: '096f208d-b3e6-451a-a36a-8b379e04d59f'
                });

                if (codeModified) {
                    $(".ide-editor").addClass('modified');
                    $("#save").addClass('btn-primary');
                    ST.trigger('change.editor');
                }
            });
        """
        r = self.session.get(self.resolve("devicetype-editor") + uuid)
        p = re.compile('ST\.DeviceIDE\.init\(\{.+?url: \'([^\']+)\',.+?websocket: \'([^\']+)\',.+?client: \'([^\']+)\',.+?id: \'([^\']+)\'', re.MULTILINE|re.IGNORECASE|re.DOTALL)
        m = p.search(r.text)

        if m:
            return {
                "url" : m.group(1),
                "websocket" : m.group(2),
                "client" : m.group(3),
                "id" : m.group(4),
                "versionid" : m.group(4), # Same as Id for some reason
                "state" : None
            }
        return None

    def uploadDeviceTypeItem(self, uuid, content, filename, path, kind):
        files = {"fileData" : (filename, content)}
        data = {
            "id" : uuid,
            "file-type|" + filename : kind,
            "file-path|" + filename : path,
            "uploadResource" : "Upload"
        }

        r = self.session.post(self.resolve("devicetype-upload"), data=data, files=files)
        if r.status_code == 200:
            return True
        return False

    def deleteDeviceTypeItem(self, uuid, item):
        r = self.session.post(self.resolve('devicetype-delete'), data={"id" : uuid, "resourceId" : item})
        if r.status_code == 200:
            return True
        return False

    def createDeviceType(self, content):
        payload = {"fromCodeType" : "code", "create" : "Create", "content" : content}
        r = self.session.post(self.resolve("devicetype-create"), data=payload, allow_redirects=False)
        if r.status_code != 302:
            print "ERROR: Unable to create item"
            return None

        p = re.compile('.*/ide/device/editor/([a-f0-9\-]+)', re.MULTILINE|re.IGNORECASE|re.DOTALL)
        m = p.match(r.headers["Location"])

        return m.group(1)

    def deleteDeviceType(self, uuid):
        payload = {"id" : uuid, "_action_delete" : "Delete"}
        r = self.session.post(self.resolve('devicetype-destroy'), data=payload, allow_redirects=False)
        if r.status_code == 302:
            return True
        return False

    def downloadSmartAppItem(self, smartapp, details, uuid):
        return self.downloadItem("smartapp-download", smartapp, details, uuid)

    def downloadDeviceTypeItem(self, devicetype, details, uuid):
        return self.downloadItem("devicetype-download", devicetype, details, uuid)

    # Convenience, downloads an entire smartapp
    def downloadBundle(self, kind, uuid, dest):
        print "Downloading bundle..."
        if kind == STServer.TYPE_SA:
            data = self.getSmartAppDetails(uuid)
        elif kind == STServer.TYPE_DTH:
            data = self.getDeviceTypeDetails(uuid)
        else:
            print "ERROR: Unsupported type"
            return False

        try:
            os.makedirs(dest)
        except:
            pass
        for i in data["flat"]:
            sys.stdout.write("  Downloading " + i + ": ")
            if kind == STServer.TYPE_SA:
                content = self.downloadSmartAppItem(uuid, data["details"], i)
            elif kind == STServer.TYPE_DTH:
                content = self.downloadDeviceTypeItem(uuid, data["details"], i)
            if content is None:
                print "Failed"
            else:
                filename = dest + content["path"] + "/" + content["filename"]
                print "OK (%s)" % content["filename"]
                try:
                    os.makedirs(dest + content["path"])
                except:
                    pass
                with open(filename, "wb") as f:
                    f.write(content["data"])
        return True

    def downloadSmartApp(self, uuid, dest):
        return self.downloadBundle(self.TYPE_SA, uuid, dest)

    def downloadDeviceType(self, uuid, dest):
        return self.downloadBundle(self.TYPE_DTH, uuid, dest)



srv = STServer("", "", "https://graph.api.smartthings.com")

srv.login()
"""
types = srv.listDeviceTypes()
for t in types.values():
    result = srv.downloadDeviceType(t["id"], "st-shell/devices/" + t["namespace"] + "/" + t["name"])

types = srv.listSmartApps()
for t in types.values():
    result = srv.downloadSmartApp(t["id"], "st-shell/smartapps/" + t["namespace"] + "/" + t["name"])
"""
#srv.createSmartApp(data)
#srv.uploadContent("19d2016d-2337-46bc-ae0e-143e033d4a63", "Hello world", "junk.txt", "", "OTHER")
#ids = srv.getSmartAppIds("19d2016d-2337-46bc-ae0e-143e033d4a63")
#srv.uploadSmartAppItem(ids['versionid'], "Hello world2", "utter_crap.png", "another", "JAVASCRIPT")
#ids = srv.getDeviceTypeIds("096f208d-b3e6-451a-a36a-8b379e04d59f")
#srv.uploadDeviceTypeItem(ids['versionid'], "Hello world2", "utter_crap.png", "another", "JAVASCRIPT")
#result = srv.createDeviceType(data)

print repr(srv.deleteDeviceType(""))
print repr(srv.deleteSmartApp(""))