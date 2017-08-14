import Queue
import json
import platform
import os
import re
import subprocess
import shutil
import threading
from collections import OrderedDict
from glob import glob
from time import sleep

from __main__ import qt, ctk, slicer

# To avoid the overhead of importing SimpleITK during application
# startup, the import of SimpleITK is delayed until it is needed.
import SimpleITK as sitk
import sitkUtils


ICON_DIR = os.path.dirname(os.path.realpath(__file__)) + '/Resources/Icons/'

from os.path import expanduser
home = expanduser("~")

DEEPINFER_DIR = os.path.join(home, '.deepinfer')
if not os.path.isdir(DEEPINFER_DIR):
    os.mkdir(DEEPINFER_DIR)

JSON_CLOUD_DIR = os.path.join(DEEPINFER_DIR, 'json', 'cloud')
if os.path.isdir(JSON_CLOUD_DIR):
    shutil.rmtree(JSON_CLOUD_DIR)
os.makedirs(JSON_CLOUD_DIR)

JSON_LOCAL_DIR = os.path.join(DEEPINFER_DIR, 'json', 'local')
if not os.path.isdir(JSON_LOCAL_DIR):
    os.makedirs(JSON_LOCAL_DIR)

TMP_PATH = os.path.join(DEEPINFER_DIR, '.tmp')
if os.path.isdir(TMP_PATH):
    shutil.rmtree(TMP_PATH)
os.mkdir(TMP_PATH)

#
# DeepInfer
#

class DeepInfer:
    # Use class-level scoped variable for module consants
    if not __file__.endswith("DeepInfer.py"):
        import inspect
        __file__ = inspect.getframeinfo(inspect.currentframe())[0]



    def __init__(self, parent):
        parent.title = "DeepInfer"
        parent.categories = ["Machine Learning"]
        parent.dependencies = []
        parent.contributors = ["Alireza Mehrtash (UBC/BWH/SPL), Mehran Pesteie (UBC)"]
        parent.helpText = \
            """
            This modules provides a basic interface to deploy machine learning and deep learning models in Slicer using Docker.
            For general information about the module see the <a href=\"{0}/Documentation/Nightly/Modules/DeepInfer\">online documentation</a>.
            <br /><br />
            For detailed information about a specific model please consult the <a href=\"http://www.deepinfer.org/\">DeepInfer website</a>.
             """.format(parent.slicerWikiUrl, slicer.app.majorVersion, slicer.app.minorVersion)

        parent.acknowledgementText = """
        The developers would like to thank the support of the Surgical Planning Lab, the University of British Columbia, Slicer Community and the Insight Toolkit.
        """
        self.parent = parent

        parent.icon = qt.QIcon("%s/ITK.png" % ICON_DIR)


#
# qDeepInferWidget
#

class DeepInferWidget:
    def __init__(self, parent=None):

        # To avoid the overhead of importing SimpleITK during application
        # startup, the import of SimpleITK is delayed until it is needed.

        if not parent:
            self.parent = slicer.qMRMLWidget()
            self.parent.setLayout(qt.QVBoxLayout())
            self.parent.setMRMLScene(slicer.mrmlScene)
        else:
            self.parent = parent
        self.layout = self.parent.layout()
        if not parent:
            self.parent.show()

        self.modelParameters = None
        self.logic = None

    def onReload(self, moduleName="DeepInfer"):
        """Generic reload method for any scripted module.
        ModuleWizard will subsitute correct default moduleName.
        """
        globals()[moduleName] = slicer.util.reloadScriptedModule(moduleName)

    def setup(self):

        # Instantiate and connect widgets ...
        #
        # Reload and Test area
        #
        reloadCollapsibleButton = ctk.ctkCollapsibleButton()
        reloadCollapsibleButton.collapsed = True
        reloadCollapsibleButton.text = "Reload && Test"
        reloadFormLayout = qt.QFormLayout(reloadCollapsibleButton)

        # reload button
        # (use this during development, but remove it when delivering
        #  your module to users)
        self.reloadButton = qt.QPushButton("Reload")
        self.reloadButton.toolTip = "Reload this module."
        self.reloadButton.name = "Freehand3DUltrasound Reload"
        reloadFormLayout.addWidget(self.reloadButton)
        self.reloadButton.connect('clicked()', self.onReload)
        # uncomment the following line for debug/development.
        self.layout.addWidget(reloadCollapsibleButton)

        # Docker Settings Area
        self.dockerGroupBox = ctk.ctkCollapsibleGroupBox()
        self.dockerGroupBox.setTitle('Docker Settings')
        self.layout.addWidget(self.dockerGroupBox)
        dockerForm = qt.QFormLayout(self.dockerGroupBox)
        self.dockerPath = ctk.ctkPathLineEdit()
        # self.dockerPath.setMaximumWidth(300)
        dockerForm.addRow("Docker Executable Path:", self.dockerPath)
        if platform.system() == 'Darwin':
            self.dockerPath.setCurrentPath('/usr/local/bin/docker')
        if platform.system() == 'Linux':
            self.dockerPath.setCurrentPath('/usr/bin/docker')
        if platform.system() == 'Windows':
            self.dockerPath.setCurrentPath("C:/Program Files/Docker/Docker/resources/bin/docker.exe")
        
        ### use nvidia-docker if it is installed
        nvidiaDockerPath = self.dockerPath.currentPath.replace('bin/docker', 'bin/nvidia-docker')
        if os.path.isfile(nvidiaDockerPath):
            self.dockerPath.setCurrentPath(nvidiaDockerPath)

        # modelRepositoryVerticalLayout = qt.QVBoxLayout(modelRepositoryExpdableArea)

        # Model Repository Area
        self.modelRepoGroupBox = ctk.ctkCollapsibleGroupBox()
        # self.modelRepoGroupBox.collapsed = True
        self.modelRepoGroupBox.setTitle('Cloud Model Repository')
        self.layout.addWidget(self.modelRepoGroupBox)
        modelRepoVBLayout1 = qt.QVBoxLayout(self.modelRepoGroupBox)
        modelRepositoryExpdableArea = ctk.ctkExpandableWidget()
        modelRepoVBLayout1.addWidget(modelRepositoryExpdableArea)
        modelRepoVBLayout2 = qt.QVBoxLayout(modelRepositoryExpdableArea)
        self.modelRegistryTable = qt.QTableWidget()
        self.modelRegistryTable.visible = False
        self.modelRepositoryModel = qt.QStandardItemModel()
        self.modelRepositoryTableHeaderLabels = ['Model', 'Organ', 'Task', 'Status']
        self.modelRegistryTable.setColumnCount(4)
        self.modelRegistryTable.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        self.modelRegistryTable.sortingEnabled = True
        self.modelRegistryTable.setHorizontalHeaderLabels(self.modelRepositoryTableHeaderLabels)
        self.modelRepositoryTableWidgetHeader = self.modelRegistryTable.horizontalHeader()
        self.modelRepositoryTableWidgetHeader.setStretchLastSection(True)
        # self.modelRepositoryTableWidgetHeader.setResizeMode(qt.QHeaderView.Stretch)
        modelRepoVBLayout2.addWidget(self.modelRegistryTable)
        #
        self.progressDownload = qt.QProgressBar()
        self.progressDownload.setRange(0, 100)
        self.progressDownload.setValue(0)
        modelRepoVBLayout2.addWidget(self.progressDownload)
        self.progressDownload.hide()
        #
        self.modelRepositoryTreeSelectionModel = self.modelRegistryTable.selectionModel()
        abstractItemView = qt.QAbstractItemView()
        self.modelRegistryTable.setSelectionBehavior(abstractItemView.SelectRows)
        verticalheader = self.modelRegistryTable.verticalHeader()
        verticalheader.setDefaultSectionSize(20)
        modelRepoVBLayout1.setSpacing(0)
        modelRepoVBLayout2.setSpacing(0)
        modelRepoVBLayout1.setMargin(0)
        modelRepoVBLayout2.setContentsMargins(7, 3, 7, 7)
        refreshWidget = qt.QWidget()
        modelRepoVBLayout2.addWidget(refreshWidget)
        hBoXLayout = qt.QHBoxLayout(refreshWidget)
        # hBoXLayout.setSpacing(0)
        # hBoXLayout.setMargin(0)
        self.connectButton = qt.QPushButton('Connect')
        self.downloadButton = qt.QPushButton('Download')
        self.downloadButton.enabled = False
        self.downloadButton.visible = False
        hBoXLayout.addStretch(1)
        hBoXLayout.addWidget(self.connectButton)
        hBoXLayout.addWidget(self.downloadButton)
        self.populateModelRegistryTable()



        #
        # Cancel/Apply Row
        #
        self.restoreDefaultsButton = qt.QPushButton("Restore Defaults")
        self.restoreDefaultsButton.toolTip = "Restore the default parameters."
        self.restoreDefaultsButton.enabled = True

        self.cancelButton = qt.QPushButton("Cancel")
        self.cancelButton.toolTip = "Abort the algorithm."
        self.cancelButton.enabled = False

        self.applyButton = qt.QPushButton("Apply")
        self.applyButton.toolTip = "Run the algorithm."
        self.applyButton.enabled = True

        hlayout = qt.QHBoxLayout()


        #
        # Local Models Area
        #
        modelsCollapsibleButton = ctk.ctkCollapsibleGroupBox()
        modelsCollapsibleButton.setTitle("Local Models")
        self.layout.addWidget(modelsCollapsibleButton)
        # Layout within the dummy collapsible button
        modelsFormLayout = qt.QFormLayout(modelsCollapsibleButton)

        # model search
        self.searchBox = ctk.ctkSearchBox()
        modelsFormLayout.addRow("Search:", self.searchBox)
        self.searchBox.connect("textChanged(QString)", self.onSearch)

        # model selector
        self.modelSelector = qt.QComboBox()
        modelsFormLayout.addRow("Model:", self.modelSelector)
        self.populateLocalModels()

        # connections
        self.modelSelector.connect('currentIndexChanged(int)', self.onModelSelect)

        #
        # Parameters Area
        #
        parametersCollapsibleButton = ctk.ctkCollapsibleGroupBox()
        parametersCollapsibleButton.setTitle("Model Parameters")
        self.layout.addWidget(parametersCollapsibleButton)

        # Layout within the dummy collapsible button
        parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)
        self.modelParameters = ModelParameters(parametersCollapsibleButton)

        # Add vertical spacer
        self.layout.addStretch(1)

        #
        # Status and Progress
        #
        statusLabel = qt.QLabel("Status: ")
        self.currentStatusLabel = qt.QLabel("Idle")
        hlayout = qt.QHBoxLayout()
        hlayout.addStretch(1)
        hlayout.addWidget(statusLabel)
        hlayout.addWidget(self.currentStatusLabel)
        self.layout.addLayout(hlayout)

        self.progress = qt.QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.layout.addWidget(self.progress)
        self.progress.hide()

        #
        # Cancel/Apply Row
        #
        self.restoreDefaultsButton = qt.QPushButton("Restore Defaults")
        self.restoreDefaultsButton.toolTip = "Restore the default parameters."
        self.restoreDefaultsButton.enabled = True

        self.cancelButton = qt.QPushButton("Cancel")
        self.cancelButton.toolTip = "Abort the algorithm."
        self.cancelButton.enabled = False

        self.applyButton = qt.QPushButton("Apply")
        self.applyButton.toolTip = "Run the algorithm."
        self.applyButton.enabled = True

        hlayout = qt.QHBoxLayout()

        hlayout.addWidget(self.restoreDefaultsButton)
        hlayout.addStretch(1)
        hlayout.addWidget(self.cancelButton)
        hlayout.addWidget(self.applyButton)
        self.layout.addLayout(hlayout)

        # connections
        self.connectButton.connect('clicked(bool)', self.onConnectButton)
        self.downloadButton.connect('clicked(bool)', self.onDownloadButton)
        self.restoreDefaultsButton.connect('clicked(bool)', self.onRestoreDefaultsButton)
        self.applyButton.connect('clicked(bool)', self.onApplyButton)
        self.cancelButton.connect('clicked(bool)', self.onCancelButton)
        self.modelRegistryTable.connect('itemSelectionChanged()', self.onCloudModelSelect)

        # Initlial Selection
        self.modelSelector.currentIndexChanged(self.modelSelector.currentIndex)

    def cleanup(self):
        pass

    def getAllDigests(self):
        cmd = []
        cmd.append(self.dockerPath.currentPath)
        cmd.append('images')
        cmd.append('--digests')
        # print(cmd)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        digest_index = 2
        digests = []
        try:
            while True:
                slicer.app.processEvents()
                line = p.stdout.readline()
                if not line:
                    break
                line = line.split()
                if 'DIGEST' in line:
                    digest_index = line.index('DIGEST')
                else:
                    digests.append(line[digest_index])
        except Exception as e:
            print("Exception: {}".format(e))
        return digests

    def populateLocalModels(self):
        digests = self.getAllDigests()
        jsonFiles = glob(JSON_LOCAL_DIR + "/*.json")
        jsonFiles.sort(cmp=lambda x, y: cmp(os.path.basename(x), os.path.basename(y)))
        self.jsonModels = []
        for fname in jsonFiles:
            with open(fname, "r") as fp:
                j = json.load(fp, object_pairs_hook=OrderedDict)
            if j['docker']['digest'] in digests:
                self.jsonModels.append(j)
            else:
                os.remove(fname)
        # add all the models listed in the json files

        for idx, j in enumerate(self.jsonModels):
            name = j["name"]
            self.modelSelector.addItem(name, idx)

    def onCloudModelSelect(self):
        self.downloadButton.enabled = False
        # print("on cloud model select!")
        for item in self.modelTableItems.keys():
            if item.isSelected():
                self.downloadButton.enabled = True
                self.selectedModelPath = self.modelTableItems[item]

    '''
    def printPythonCommand(self):
        self.modelParameters.prrun()  # Do this first!
        printStr = []
        currentModel = self.modelParameters.model
        varName = currentModel.__class__.__name__
        printStr.append('myModel = {0}()'.format(varName))
        for key in dir(currentModel):
            if key == 'GetName' or key.startswith('GetGlobal'):
                pass
            elif key[:3] == 'Get':
                setAttr = key.replace("Get", "Set", 1)
                if hasattr(currentModel, setAttr):
                    value = eval("currentModel.{0}()".format(key))
                    printStr.append('myModel.{0}({1})'.format(setAttr, value))

        print("\n".join(printStr))
    '''

    def onLogicRunStop(self):
        self.applyButton.setEnabled(True)
        self.restoreDefaultsButton.setEnabled(True)
        self.cancelButton.setEnabled(False)
        self.logic = None
        self.progress.hide()

    def onLogicRunStart(self):
        self.applyButton.setEnabled(False)
        self.restoreDefaultsButton.setEnabled(False)

    def onSearch(self, searchText):
        # add all the models listed in the json files
        self.modelSelector.clear()
        # split text on whitespace of and string search
        searchTextList = searchText.split()
        for idx, j in enumerate(self.jsonModels):
            lname = j["name"].lower()
            # require all elements in list, to add to select. case insensitive
            if reduce(lambda x, y: x and (lname.find(y.lower()) != -1), [True] + searchTextList):
                self.modelSelector.addItem(j["name"], idx)

    def onModelSelect(self, selectorIndex):
        # print("on model select")
        self.modelParameters.destroy()
        if selectorIndex < 0:
            return
        jsonIndex = self.modelSelector.itemData(selectorIndex)
        json_model = self.jsonModels[jsonIndex]
        self.modelParameters.create(json_model)

        if "briefdescription" in self.jsonModels[jsonIndex]:
            tip = self.jsonModels[jsonIndex]["briefdescription"]
            tip = tip.rstrip()
            self.modelSelector.setToolTip(tip)
        else:
            self.modelSelector.setToolTip("")

    def onConnectButton(self):
        try:
            self.modelRegistryTable.visible = True
            self.downloadButton.visible = True
            self.connectButton.visible = False
            self.connectButton.enabled = False
            import urllib2
            url = 'https://api.github.com/repos/DeepInfer/Model-Registry/contents/'
            response = urllib2.urlopen(url)
            data = json.load(response)
            for item in data:
                if 'json' in item['name']:
                    # print(item['name'])
                    url = item['url']
                    response = urllib2.urlopen(url)
                    data = json.load(response)
                    dl_url = data['download_url']
                    print("downloading: {}...".format(dl_url))
                    response = urllib2.urlopen(dl_url)
                    content = response.read()
                    outputPath = os.path.join(JSON_CLOUD_DIR, dl_url.split('/')[-1])
                    with open(outputPath, 'w') as f:
                        f.write(content)
            self.populateModelRegistryTable()
        except Exception as e:
            print("Exception occured: {}".format(e))
            self.connectButton.enabled = True
            self.modelRegistryTable.visible = False
            self.downloadButton.visible = False
            self.connectButton.visible = True
        self.connectButton.enabled = True

    def onDownloadButton(self):
        with open(self.selectedModelPath) as json_data:
            model = json.load(json_data)
        size = model['docker']['size']
        resoponse = self.Question("The size of the selected image to download is {}. Are you sure you want to proceed?".format(size),
                      title="Download", parent=None)
        if resoponse:
            cmd = []
            cmd.append(self.dockerPath.currentPath)
            cmd.append('pull')
            cmd.append(model['docker']['dockerhub_repository'] + '@' + model['docker']['digest'])
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            print(cmd)
            parts = dict()
            try:
                while True:
                    self.progressDownload.show()
                    slicer.app.processEvents()
                    line = p.stdout.readline()
                    if not line:
                        break
                    line = line.rstrip()
                    print(line)
                    part = line.split(':')[0]
                    if len(part) == 12:
                        parts[part] = line.split(':')[1]
                    if parts.keys():
                        print('-'*100)
                        print(parts)
                        n_parts = len(parts.keys())
                        n_completed = len([status for status in parts.values() if status == ' Pull complete'])
                        self.progressDownload.setValue(int((100*n_completed)/n_parts))

            except Exception as e:
                print("Exception: {}".format(e))
            print(parts)
            self.progressDownload.setValue(0)
            self.progressDownload.hide()
            shutil.copy(self.selectedModelPath, os.path.join(JSON_LOCAL_DIR, os.path.basename(self.selectedModelPath)))
            self.populateLocalModels()
        else:
            print("Download was canceled!")

    def Question(self, text, title="", parent=None):
        return qt.QMessageBox.question(parent, title, text,
                                   qt.QMessageBox.Yes, qt.QMessageBox.No) == qt.QMessageBox.Yes

    def populateModelRegistryTable(self):
        self.modelTableItems = dict()
        # print("populate Model Registry Table")
        model_files = glob(JSON_CLOUD_DIR+'/*.json')
        self.modelRegistryTable.setRowCount(len(model_files))
        n = 0
        model_files = [os.path.join(JSON_CLOUD_DIR, model_file) for model_file in model_files]
        for model_file in model_files:
            with open(model_file) as json_data:
                model = json.load(json_data)
            keys = model.keys()
            for key in keys:
                if key == 'name':
                    nameTableItem = qt.QTableWidgetItem(str(model['name']))
                    self.modelTableItems[nameTableItem] = model_file
                    self.modelRegistryTable.setItem(n, 0, nameTableItem)
                if key == 'organ':
                    organ = qt.QTableWidgetItem(str(model['organ']))
                    self.modelRegistryTable.setItem(n, 1, organ)
                if key == 'task':
                    task = qt.QTableWidgetItem(str(model['task']))
                    self.modelRegistryTable.setItem(n, 2, task)
            n += 1

    def onRestoreDefaultsButton(self):
        self.onModelSelect(self.modelSelector.currentIndex)

    def onApplyButton(self):
        print('onApply')
        self.logic = DeepInferLogic()
        # try:
        self.currentStatusLabel.text = "Starting"
        self.modelParameters.prerun()
        self.logic.run(self.modelParameters)

        '''
        except:
            self.currentStatusLabel.text = "Exception"
            slicer.modules.DeepInferWidget.applyButton.enabled = True
            import sys
            msg = sys.exc_info()[0]
            # if there was an exception during start-up make sure to finish
            self.onLogicRunStop()
            qt.QMessageBox.critical(slicer.util.mainWindow(),
                                    "Exception before execution: {0} ".format(self.modelParameters.dockerImageName),
                                    msg)
        '''

    def onCancelButton(self):
        self.currentStatusLabel.text = "Aborting"
        if self.logic:
            self.logic.abort = True;

    def onLogicEventStart(self):
        self.currentStatusLabel.text = "Running"
        self.cancelButton.setDisabled(False)
        self.progress.setValue(0)
        self.progress.show()

    def onLogicEventEnd(self):
        self.currentStatusLabel.text = "Completed"
        self.progress.setValue(1000)

    def onLogicEventAbort(self):
        self.currentStatusLabel.text = "Aborted"

    def onLogicEventProgress(self, progress):
        self.currentStatusLabel.text = "Running ({0:6.5f})".format(progress)
        self.progress.setValue(progress * 1000)

    def onLogicEventIteration(self, nIter):
        print("Iteration ", nIter)

#
# DeepInferLogic
#

class DeepInferLogic:
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget
    """

    def __init__(self):
        self.main_queue = Queue.Queue()
        self.main_queue_running = False
        self.thread = threading.Thread()
        self.abort = False
        modules = slicer.modules
        if hasattr(modules, 'DeepInferWidget'):
            self.dockerPath = slicer.modules.DeepInferWidget.dockerPath.currentPath
        else:
            if platform.system() == 'Darwin':
                defualt_path = '/usr/local/bin/docker'
                self.setDockerPath(defualt_path)
            elif platform.system() == 'Linux':
                defualt_path = '/usr/bin/docker'
                self.setDockerPath(defualt_path)
            elif platform.system() == 'Windows':
                defualt_path = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
                self.setDockerPath(defualt_path)
            else:
                print('could not determine system type')


    def __del__(self):
        if self.main_queue_running:
            self.main_queue_stop()
        if self.thread.is_alive():
            self.thread.join()

    def setDockerPath(self, path):
        self.dockerPath = path

    def yieldPythonGIL(self, seconds=0):
        sleep(seconds)

    def cmdCheckAbort(self, p):
        if self.abort:
            p.kill()
            self.cmdAbortEvent()

    def cmdStartEvent(self):
        widget = slicer.modules.DeepInferWidget
        widget.onLogicEventStart()
        self.yieldPythonGIL()

    def cmdProgressEvent(self, progress):
        widget = slicer.modules.DeepInferWidget
        widget.onLogicEventProgress(progress)
        self.yieldPythonGIL()

    def cmdAbortEvent(self):
        widget = slicer.modules.DeepInferWidget
        widget.onLogicEventAbort()
        self.yieldPythonGIL()

    def cmdEndEvent(self):
        widget = slicer.modules.DeepInferWidget
        widget.onLogicEventEnd()
        self.yieldPythonGIL()

    def checkDockerDaemon(self):
        cmd = list()
        cmd.append(self.dockerPath)
        cmd.append('ps')
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        slicer.app.processEvents()
        line = p.stdout.readline()
        if line[:9] == 'CONTAINER':
            return True
        return False

    def executeDocker(self, dockerName, modelName, dataPath, iodict, inputs, params):
        assert self.checkDockerDaemon(), "Docker Daemon is not running"
        modules = slicer.modules
        if hasattr(modules, 'DeepInferWidget'):
            widgetPresent = True
        else:
            widgetPresent = False
       
        if widgetPresent:
            self.cmdStartEvent()
        inputDict = dict()
        outputDict = dict()
        paramDict = dict()
        for item in iodict:
            # print(item)
            if iodict[item]["iotype"] == "input":
                if iodict[item]["type"] == "volume":
                    # print(inputs[item])
                    input_node_name = inputs[item].GetName()
                    #try:
                    img = sitk.ReadImage(sitkUtils.GetSlicerITKReadWriteAddress(input_node_name))
                    fileName = item + '.nrrd'
                    inputDict[item] = fileName
                    sitk.WriteImage(img, str(os.path.join(TMP_PATH, fileName)))
                    #except Exception as e:
                    #    print(e.message)
            elif iodict[item]["iotype"] == "output":
                if iodict[item]["type"] == "volume":
                      fileName = item + '.nrrd'
                      outputDict[item] = fileName
            elif iodict[item]["iotype"] == "parameter":
                paramDict[item] = params[item]

        if not dataPath:
            dataPath = '/home/deepinfer/data'

        print('docker run command:')
        cmd = list()
        cmd.append(self.dockerPath)
        cmd.extend(('run', '-t', '-v'))
        cmd.append(TMP_PATH + ':' + dataPath)
        cmd.append(dockerName)
        for key in inputDict.keys():
            cmd.append('--' + key)
            cmd.append(dataPath + '/' + inputDict[key])
        for key in outputDict.keys():
            cmd.append('--' + key)
            cmd.append(dataPath + '/' + outputDict[key])
        if modelName:
            cmd.append('--ModelName')
            cmd.append(modelName)
        for key in paramDict.keys():
            if iodict[key]["type"] == "bool":
                if paramDict[key]:
                    cmd.append('--' + key)
            else:
                cmd.append('--' + key)
                cmd.append(paramDict[key])
        print('-'*100)
        print(cmd)

        # TODO: add a line to check wether the docker image is present or not. If not ask user to download it.
        # try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        progress = 0
        # print('executing')
        while True:
            progress += 0.15
            slicer.app.processEvents()
            self.cmdCheckAbort(p)
            if widgetPresent:
                self.cmdProgressEvent(progress)
            line = p.stdout.readline()
            if not line:
                break
            print(line)
        #except Exception as e:
        #    msg = e.message
        #    self.abort = True
        #    qt.QMessageBox.critical(slicer.util.mainWindow(), "Exception during execution of ", msg)

    def thread_doit(self, modelParameters):
        iodict = modelParameters.iodict
        inputs = modelParameters.inputs
        params = modelParameters.params
        outputs = modelParameters.outputs
        dockerName = modelParameters.dockerImageName
        modelName = modelParameters.modelName
        dataPath = modelParameters.dataPath
        #try:
        self.main_queue_start()
        self.executeDocker(dockerName, modelName, dataPath, iodict, inputs, params)
        if not self.abort:
            self.updateOutput(iodict, outputs)
            self.main_queue_stop()
            self.cmdEndEvent()

        '''
        except Exception as e:
            msg = e.message
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Exception during execution of ", msg)
            slicer.modules.DeepInferWidget.applyButton.enabled = True
            slicer.modules.DeepInferWidget.progress.hide = True
            self.abort = True
            self.yieldPythonGIL()
        '''
    def main_queue_start(self):
        """Begins monitoring of main_queue for callables"""
        self.main_queue_running = True
        slicer.modules.DeepInferWidget.onLogicRunStart()
        qt.QTimer.singleShot(0, self.main_queue_process)

    def main_queue_stop(self):
        """End monitoring of main_queue for callables"""
        self.main_queue_running = False
        if self.thread.is_alive():
            self.thread.join()
        slicer.modules.DeepInferWidget.onLogicRunStop()

    def main_queue_process(self):
        """processes the main_queue of callables"""
        try:
            while not self.main_queue.empty():
                f = self.main_queue.get_nowait()
                if callable(f):
                    f()

            if self.main_queue_running:
                # Yield the GIL to allow other thread to do some python work.
                # This is needed since pyQt doesn't yield the python GIL
                self.yieldPythonGIL(.01)
                qt.QTimer.singleShot(0, self.main_queue_process)

        except Exception as e:
            import sys
            sys.stderr.write("ModelLogic error in main_queue: \"{0}\"".format(e))

            # if there was an error try to resume
            if not self.main_queue.empty() or self.main_queue_running:
                qt.QTimer.singleShot(0, self.main_queue_process)

    def updateOutput(self, iodict, outputs):
        # print('updateOutput method')
        output_volume_files = dict()
        for item in iodict:
            if iodict[item]["iotype"] == "output":
                if iodict[item]["type"] == "volume":
                    fileName = str(os.path.join(TMP_PATH, item + '.nrrd'))
                    output_volume_files[item] = fileName
        for output_volume in output_volume_files.keys():
            result = sitk.ReadImage(output_volume_files[output_volume])
            output_node = outputs[output_volume]
            output_node_name = output_node.GetName()
            nodeWriteAddress = sitkUtils.GetSlicerITKReadWriteAddress(output_node_name)
            sitk.WriteImage(result, nodeWriteAddress)
            applicationLogic = slicer.app.applicationLogic()
            selectionNode = applicationLogic.GetSelectionNode()

            outputLabelMap = True
            if outputLabelMap:
                selectionNode.SetReferenceActiveLabelVolumeID(output_node.GetID())
            else:
                selectionNode.SetReferenceActiveVolumeID(output_node.GetID())

            applicationLogic.PropagateVolumeSelection(0)
            applicationLogic.FitSliceToAll()

    def run(self, modelParamters):
        """
        Run the actual algorithm
        """
        if self.thread.is_alive():
            import sys
            sys.stderr.write("ModelLogic is already executing!")
            return
        self.abort = False
        self.thread = threading.Thread(target=self.thread_doit(modelParameters=modelParamters))


#
# Class to manage parameters
#

class ModelParameters(object):
    """ This class is for managing the widgets for the parameters for a model
    """

    # class-scope regular expression to help covert from CamelCase
    reCamelCase = re.compile('((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))')

    def __init__(self, parent=None):
        self.parent = parent
        self.widgets = []
        self.json = None
        # self.model = None
        self.inputs = []
        self.outputs = []
        self.prerun_callbacks = []
        self.outputLabelMap = False
        self.iodict = dict()
        self.dockerImageName = ''
        self.modelName = None
        self.dataPath = None

        self.outputSelector = None
        self.outputLabelMapBox = None


    def __del__(self):
        self.widgets = []

    def BeautifyCamelCase(self, str):
        return self.reCamelCase.sub(r' \1', str)

    def create_iodict(self, json_dict):
        iodict = dict()
        for member in json_dict["members"]:
            if "type" in member:
                t = member["type"]
                if t in ["uint8_t", "int8_t",
                           "uint16_t", "int16_t",
                           "uint32_t", "int32_t",
                           "uint64_t", "int64_t",
                           "unsigned int", "int",
                           "double", "float"]:
                    iodict[member["param_name"]] = {"type": member["type"], "iotype": member["iotype"],
                                                            "value": member["default"]}

                else:
                    iodict[member["name"]] = {"type": member["type"], "iotype": member["iotype"]}
        self.iodict = iodict

    def create_model_info(self, json_dict):
        self.dockerImageName = json_dict['docker']['dockerhub_repository']
        self.modelName = json_dict.get('model_name')
        self.dataPath = json_dict.get('data_path')

    def create(self, json_dict):
        if not self.parent:
            raise "no parent"
            # parametersFormLayout = self.parent.layout()

        # You can't use exec in a function that has a subfunction, unless you specify a context.
        # exec ('self.model = sitk.{0}()'.format(json["name"])) in globals(), locals()

        self.create_iodict(json_dict)
        self.create_model_info(json_dict)

        self.prerun_callbacks = []
        self.inputs = dict()
        self.outputs = dict()
        self.params = dict()
        self.outputLabelMap = False

        #
        # Iterate over the members in the JSON to generate a GUI
        #
        for member in json_dict["members"]:
            w = None
            if "type" in member:
                t = member["type"]

            if "dim_vec" in member and int(member["dim_vec"]):
                if member["itk_type"].endswith("IndexType") or member["itk_type"].endswith("PointType"):
                    isPoint = member["itk_type"].endswith("PointType")

                    fiducialSelector = slicer.qMRMLNodeComboBox()
                    self.widgets.append(fiducialSelector)
                    fiducialSelector.nodeTypes = ("vtkMRMLMarkupsFiducialNode", "vtkMRMLAnnotationFiducialNode")
                    fiducialSelector.selectNodeUponCreation = True
                    fiducialSelector.addEnabled = False
                    fiducialSelector.removeEnabled = False
                    fiducialSelector.renameEnabled = True
                    fiducialSelector.noneEnabled = False
                    fiducialSelector.showHidden = False
                    fiducialSelector.showChildNodeTypes = True
                    fiducialSelector.setMRMLScene(slicer.mrmlScene)
                    fiducialSelector.setToolTip("Pick the Fiducial for the Point or Index")

                    fiducialSelector.connect("nodeActivated(vtkMRMLNode*)",
                                             lambda node, w=fiducialSelector, name=member["name"],
                                                    isPt=isPoint: self.onFiducialNode(name, w, isPt))
                    self.prerun_callbacks.append(
                        lambda w=fiducialSelector, name=member["name"], isPt=isPoint: self.onFiducialNode(name, w,
                                                                                                          isPt))

                    w1 = fiducialSelector

                    fiducialSelectorLabel = qt.QLabel("{0}: ".format(member["name"]))
                    self.widgets.append(fiducialSelectorLabel)

                    icon = qt.QIcon(ICON_DIR + "Fiducials.png")

                    toggle = qt.QPushButton(icon, "")
                    toggle.setCheckable(True)
                    toggle.toolTip = "Toggle Fiducial Selection"
                    self.widgets.append(toggle)

                    w2 = self.createVectorWidget(member["name"], t)

                    hlayout = qt.QHBoxLayout()
                    hlayout.addWidget(fiducialSelector)
                    hlayout.setStretchFactor(fiducialSelector, 1)
                    hlayout.addWidget(w2)
                    hlayout.setStretchFactor(w2, 1)
                    hlayout.addWidget(toggle)
                    hlayout.setStretchFactor(toggle, 0)
                    w1.hide()

                    self.widgets.append(hlayout)

                    toggle.connect("clicked(bool)",
                                   lambda checked, ptW=w2, fidW=w1: self.onToggledPointSelector(checked, ptW, fidW))

                    # parametersFormLayout.addRow(fiducialSelectorLabel, hlayout)

                else:
                    w = self.createVectorWidget(member["name"], t)

            elif "point_vec" in member:

                fiducialSelector = slicer.qMRMLNodeComboBox()
                self.widgets.append(fiducialSelector)
                fiducialSelector.nodeTypes = ("vtkMRMLMarkupsFiducialNode", "vtkMRMLAnnotationHierarchyNode")
                fiducialSelector.addAttribute("vtkMRMLAnnotationHierarchyNode", "MainChildType",
                                              "vtkMRMLAnnotationFiducialNode")
                fiducialSelector.selectNodeUponCreation = True
                fiducialSelector.addEnabled = True
                fiducialSelector.removeEnabled = False
                fiducialSelector.renameEnabled = True
                fiducialSelector.noneEnabled = False
                fiducialSelector.showHidden = False
                fiducialSelector.showChildNodeTypes = True
                fiducialSelector.setMRMLScene(slicer.mrmlScene)
                fiducialSelector.setToolTip("Pick the Markups node for the point list.")

                fiducialSelector.connect("nodeActivated(vtkMRMLNode*)",
                                         lambda node, name=member["name"]: self.onFiducialListNode(name, node))
                self.prerun_callbacks.append(
                    lambda w=fiducialSelector, name=member["name"], : self.onFiducialListNode(name, w.currentNode()))

                w = fiducialSelector

            elif "enum" in member:
                w = self.createEnumWidget(member["name"], member["enum"])

            elif member["name"].endswith("Direction") and "std::vector" in t:
                # This member name is use for direction cosine matrix for image sources.
                # We are going to ignore it
                pass
            elif t == "volume":
                w = self.createVolumeWidget(member["name"], member["iotype"], member["voltype"], False)

            elif t == "InterpolatorEnum":
                labels = ["Nearest Neighbor",
                          "Linear",
                          "BSpline",
                          "Gaussian",
                          "Label Gaussian",
                          "Hamming Windowed Sinc",
                          "Cosine Windowed Sinc",
                          "Welch Windowed Sinc",
                          "Lanczos Windowed Sinc",
                          "Blackman Windowed Sinc"]
                values = ["sitk.sitkNearestNeighbor",
                          "sitk.sitkLinear",
                          "sitk.sitkBSpline",
                          "sitk.sitkGaussian",
                          "sitk.sitkLabelGaussian",
                          "sitk.sitkHammingWindowedSinc",
                          "sitk.sitkCosineWindowedSinc",
                          "sitk.sitkWelchWindowedSinc",
                          "sitk.sitkLanczosWindowedSinc",
                          "sitk.sitkBlackmanWindowedSinc"]

                w = self.createEnumWidget(member["name"], labels, values)
                pass
            elif t == "PixelIDValueEnum":
                labels = ["int8_t",
                          "uint8_t",
                          "int16_t",
                          "uint16_t",
                          "uint32_t",
                          "int32_t",
                          "float",
                          "double"]
                values = ["sitk.sitkInt8",
                          "sitk.sitkUInt8",
                          "sitk.sitkInt16",
                          "sitk.sitkUInt16",
                          "sitk.sitkInt32",
                          "sitk.sitkUInt32",
                          "sitk.sitkFloat32",
                          "sitk.sitkFloat64"]
                w = self.createEnumWidget(member["name"], labels, values)
            elif t in ["double", "float"]:
                w = self.createDoubleWidget(member["param_name"], default=member["default"])
            elif t == "bool":
                w = self.createBoolWidget(member["name"], default=member["default"])
            elif t in ["uint8_t", "int8_t",
                       "uint16_t", "int16_t",
                       "uint32_t", "int32_t",
                       "uint64_t", "int64_t",
                       "unsigned int", "int"]:
                w = self.createIntWidget(member["param_name"], t, default=member["default"])
            else:
                import sys
                sys.stderr.write("Unknown member \"{0}\" of type \"{1}\"\n".format(member["name"], member["type"]))

            if w:
                self.addWidgetWithToolTipAndLabel(w, member)

    def createVolumeWidget(self, name, iotype, voltype, noneEnabled=False):
        # print("create volume widget : {0}".format(name))
        volumeSelector = slicer.qMRMLNodeComboBox()
        self.widgets.append(volumeSelector)
        if voltype == 'ScalarVolume':
            volumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode", ]
        elif voltype == 'LabelMap':
            volumeSelector.nodeTypes = ["vtkMRMLLabelMapVolumeNode", ]
        else:
            print('Voltype must be either ScalarVolume or LabelMap!')
        volumeSelector.selectNodeUponCreation = True
        if iotype == "input":
            volumeSelector.addEnabled = False
        elif iotype == "output":
            volumeSelector.addEnabled = True
        volumeSelector.removeEnabled = True
        volumeSelector.noneEnabled = noneEnabled
        volumeSelector.showHidden = False
        volumeSelector.showChildNodeTypes = False
        volumeSelector.setMRMLScene(slicer.mrmlScene)
        volumeSelector.setToolTip("Pick the volume.")

        # connect and verify parameters
        volumeSelector.connect("currentNodeChanged(vtkMRMLNode*)",
                               lambda node, n=name, io=iotype: self.onVolumeSelect(node, n, io))
        if iotype == "input":
            self.inputs[name] = volumeSelector.currentNode()
        elif iotype == "output":
            self.outputs[name] = volumeSelector.currentNode()

        return volumeSelector

    def createEnumWidget(self, name, enumList, valueList=None):

        w = qt.QComboBox()
        self.widgets.append(w)

        # exec 'default=self.model.Get{0}()'.format(name) in globals(), locals()

        if valueList is None:
            valueList = ["self.model." + e for e in enumList]

        for e, v in zip(enumList, valueList):
            w.addItem(e, v)

        self.params[name] = w.currentText
        w.connect("currentIndexChanged(int)",
                  lambda selectorIndex, n=name, selector=w: self.onEnumChanged(n, selectorIndex, selector))
        return w

    def createVectorWidget(self, name, type):
        m = re.search(r"<([a-zA-Z ]+)>", type)
        if m:
            type = m.group(1)

        w = ctk.ctkCoordinatesWidget()
        self.widgets.append(w)

        if type in ["double", "float"]:
            w.setDecimals(5)
            w.minimum = -3.40282e+038
            w.maximum = 3.40282e+038
            w.connect("coordinatesChanged(double*)",
                      lambda val, widget=w, name=name: self.onFloatVectorChanged(name, widget, val))
        elif type == "bool":
            w.setDecimals(0)
            w.minimum = 0
            w.maximum = 1
            w.connect("coordinatesChanged(double*)",
                      lambda val, widget=w, name=name: self.onBoolVectorChanged(name, widget, val))
        else:
            w.setDecimals(0)
            w.connect("coordinatesChanged(double*)",
                      lambda val, widget=w, name=name: self.onIntVectorChanged(name, widget, val))

        # exec ('default = self.model.Get{0}()'.format(name)) in globals(), locals()
        # w.coordinates = ",".join(str(x) for x in default)
        return w

    def createIntWidget(self, name, type="int", default=None):

        w = qt.QSpinBox()
        self.widgets.append(w)

        if type == "uint8_t":
            w.setRange(0, 255)
        elif type == "int8_t":
            w.setRange(-128, 127)
        elif type == "uint16_t":
            w.setRange(0, 65535)
        elif type == "int16_t":
            w.setRange(-32678, 32767)
        elif type == "uint32_t" or type == "uint64_t" or type == "unsigned int":
            w.setRange(0, 2147483647)
        elif type == "int32_t" or type == "uint64_t" or type == "int":
            w.setRange(-2147483648, 2147483647)

        # exec ('default = self.model.Get{0}()'.format(name)) in globals(), locals()
        if default is not None:
            w.setValue(int(default))
        w.connect("valueChanged(int)", lambda val, name=name: self.onScalarChanged(name, val))
        return w

    def createBoolWidget(self, name, default):
        # print('create bool widget')
        w = qt.QCheckBox()
        self.widgets.append(w)
        if default == 'false':
            checked = False
        else:
            checked = True
        w.setChecked(checked)
        self.params[name] = int(w.checked)
        w.connect("stateChanged(int)", lambda val, name=name: self.onScalarChanged(name, int(val)))

        return w

    def createDoubleWidget(self, name, default=None):
        # exec ('default = self.model.Get{0}()'.format(name)) in globals(), locals()
        w = qt.QDoubleSpinBox()
        self.widgets.append(w)

        w.setRange(-3.40282e+038, 3.40282e+038)
        w.decimals = 5

        if default is not None:
            w.setValue(default)
        w.connect("valueChanged(double)", lambda val, name=name: self.onScalarChanged(name, val))

        return w

    def addWidgetWithToolTipAndLabel(self, widget, memberJSON):
        tip = ""
        if "briefdescriptionSet" in memberJSON and len(memberJSON["briefdescriptionSet"]):
            tip = memberJSON["briefdescriptionSet"]
        elif "detaileddescriptionSet" in memberJSON:
            tip = memberJSON["detaileddescriptionSet"]

        # remove trailing white space
        tip = tip.rstrip()

        l = qt.QLabel(self.BeautifyCamelCase(memberJSON["name"]) + ": ")
        self.widgets.append(l)

        widget.setToolTip(tip)
        l.setToolTip(tip)

        parametersFormLayout = self.parent.layout()
        parametersFormLayout.addRow(l, widget)

    def onToggledPointSelector(self, fidVisible, ptWidget, fiducialWidget):
        ptWidget.setVisible(False)
        fiducialWidget.setVisible(False)

        ptWidget.setVisible(not fidVisible)
        fiducialWidget.setVisible(fidVisible)

        if ptWidget.visible:
            # Update the coordinate values to envoke the changed signal.
            # This will update the model from the widget
            ptWidget.coordinates = ",".join(str(x) for x in ptWidget.coordinates.split(','))

    def onVolumeSelect(self, mrmlNode, n, io):
        # print("on volume select:{}".format(n))
        if io == "input":
            self.inputs[n] = mrmlNode
        elif io == "output":
            self.outputs[n] = mrmlNode

    '''
    def onOutputSelect(self, mrmlNode):
        self.output = mrmlNode
        self.onOutputLabelMapChanged(mrmlNode.IsA("vtkMRMLLabelMapVolumeNode"))

    def onOutputLabelMapChanged(self, v):
        self.outputLabelMap = v
        self.outputLabelMapBox.setChecked(v)
    '''

    def onFiducialNode(self, name, mrmlWidget, isPoint):
        if not mrmlWidget.visible:
            return
        annotationFiducialNode = mrmlWidget.currentNode()

        # point in physical space
        coord = [0, 0, 0]

        if annotationFiducialNode.GetClassName() == "vtkMRMLMarkupsFiducialNode":
            # slicer4 Markups node
            if annotationFiducialNode.GetNumberOfFiducials() < 1:
                return
            annotationFiducialNode.GetNthFiducialPosition(0, coord)
        else:
            annotationFiducialNode.GetFiducialCoordinates(coord)

        # HACK transform from RAS to LPS
        coord = [-coord[0], -coord[1], coord[2]]

        # FIXME: we should not need to copy the image
        if not isPoint and len(self.inputs) and self.inputs[0]:
            imgNodeName = self.inputs[0].GetName()
            img = sitk.ReadImage(sitkUtils.GetSlicerITKReadWriteAddress(imgNodeName))
            coord = img.TransformPhysicalPointToIndex(coord)
            # exec ('self.model.Set{0}(coord)'.format(name))

    def onFiducialListNode(self, name, mrmlNode):
        annotationHierarchyNode = mrmlNode

        # list of points in physical space
        coords = []

        if annotationHierarchyNode.GetClassName() == "vtkMRMLMarkupsFiducialNode":
            # slicer4 Markups node

            for i in range(annotationHierarchyNode.GetNumberOfFiducials()):
                coord = [0, 0, 0]
                annotationHierarchyNode.GetNthFiducialPosition(i, coord)
                coords.append(coord)
        else:
            # slicer4 style hierarchy nodes

            # get the first in the list
            for listIndex in range(annotationHierarchyNode.GetNumberOfChildrenNodes()):
                if annotationHierarchyNode.GetNthChildNode(listIndex) is None:
                    continue

                annotation = annotationHierarchyNode.GetNthChildNode(listIndex).GetAssociatedNode()
                if annotation is None:
                    continue

                coord = [0, 0, 0]
                annotation.GetFiducialCoordinates(coord)
                coords.append(coord)

        if self.inputs[0]:
            imgNodeName = self.inputs[0].GetName()
            img = sitk.ReadImage(sitkUtils.GetSlicerITKReadWriteAddress(imgNodeName))

            # HACK transform from RAS to LPS
            coords = [[-pt[0], -pt[1], pt[2]] for pt in coords]

            idx_coords = [img.TransformPhysicalPointToIndex(pt) for pt in coords]

            # exec ('self.model.Set{0}(idx_coords)'.format(name))

    def onScalarChanged(self, name, val):
        # exec ('self.model.Set{0}(val)'.format(name))
        # print("onScalarChanged")
        self.params[name] = val

    def onEnumChanged(self, name, selectorIndex, selector):
        # data = selector.itemData(selectorIndex)
        self.params[name] = selector.currentText

    def onBoolVectorChanged(self, name, widget, val):
        coords = [bool(float(x)) for x in widget.coordinates.split(',')]
        # exec ('self.model.Set{0}(coords)'.format(name))

    def onIntVectorChanged(self, name, widget, val):
        coords = [int(float(x)) for x in widget.coordinates.split(',')]
        # exec ('self.model.Set{0}(coords)'.format(name))

    def onFloatVectorChanged(self, name, widget, val):
        coords = [float(x) for x in widget.coordinates.split(',')]
        # exec ('self.model.Set{0}(coords)'.format(name))

    def prerun(self):
        print('prerun...')
        for f in self.prerun_callbacks:
            f()

    def destroy(self):
        self.iodict = dict()
        self.inputs = dict()
        self.outputs = dict()
        for w in self.widgets:
            # self.parent.layout().removeWidget(w)
            w.deleteLater()
            w.setParent(None)
        self.widgets = []
