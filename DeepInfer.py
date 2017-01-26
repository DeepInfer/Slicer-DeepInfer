import os, sys
import unittest
from __main__ import vtk, qt, ctk, slicer
from glob import glob
import json
from collections import OrderedDict
import re
import threading
import Queue
from time import sleep

# To avoid the overhead of importing SimpleITK during application
# startup, the import of SimpleITK is delayed until it is needed.
sitk = None
sitkUtils = None


#
# DeepInfer
#

class DeepInfer:
    # Use class-level scoped variable for module consants
    if not __file__.endswith("DeepInfer.py"):
        import inspect
        __file__ = inspect.getframeinfo(inspect.currentframe())[0]

    ICON_DIR = os.path.dirname(os.path.realpath(__file__)) + '/Resources/Icons/'
    JSON_DIR = os.path.dirname(os.path.realpath(__file__)) + '/Resources/json/'

    def __init__(self, parent):
        parent.title = "DeepInfer"
        parent.categories = ["Wizards"]
        parent.dependencies = []
        parent.contributors = ["Alireza Mehrtash (UBC/BWH/SPL), Mehran Pesteie (UBC)"]
        parent.helpText = \
            """
            This modules provides a basic interface to

            For general information about the module see the <a href=\"{0}/Documentation/Nightly/Modules/DeepInfer\">online documentation</a>.
            <br /><br />

            For detailed information about a specific model please consult the <a href=\"http://www.deepinfer.org/\">Insight Toolkit Doxygen</a>.
             """.format(parent.slicerWikiUrl, slicer.app.majorVersion, slicer.app.minorVersion)

        parent.acknowledgementText = """
The developers would like to thank the support of the Slicer Community, the Insight Toolkit and the ITK Community."
"""  # replace with organization, grant and thanks.
        self.parent = parent

        parent.icon = qt.QIcon("%s/ITK.png" % self.ICON_DIR)


#
# qDeepInferWidget
#

class DeepInferWidget:
    def __init__(self, parent=None):

        # To avoid the overhead of importing SimpleITK during application
        # startup, the import of SimpleITK is delayed until it is needed.
        global sitk
        import SimpleITK as sitk
        global sitkUtils
        import sitkUtils

        if not parent:
            self.parent = slicer.qMRMLWidget()
            self.parent.setLayout(qt.QVBoxLayout())
            self.parent.setMRMLScene(slicer.mrmlScene)
        else:
            self.parent = parent
        self.layout = self.parent.layout()
        if not parent:
            self.setup()
            self.parent.show()

        jsonFiles = glob(DeepInfer.JSON_DIR + "*.json")
        jsonFiles.sort(cmp=lambda x, y: cmp(os.path.basename(x), os.path.basename(y)))

        self.jsonModels = []

        for fname in jsonFiles:
            try:
                fp = file(fname, "r")
                j = json.load(fp, object_pairs_hook=OrderedDict)
                #if j["name"] in dir(sitk):
                if True:
                    self.jsonModels.append(j)
                else:
                    import sys
                    sys.stderr.write("Unknown SimpleITK class \"{0}\".\n".format(j["name"]))
            except Exception as e:
                import sys
                sys.stderr.write("Error while reading \"{0}\". Exception: {1}\n".format(fname, e))

        self.modelParameters = None
        self.logic = None

    def onReload(self, moduleName="DeepInfer"):
        """Generic reload method for any scripted module.
        ModuleWizard will subsitute correct default moduleName.
        """
        globals()[moduleName] = slicer.util.reloadScriptedModule(moduleName)

    def setup(self):
        #
        # Reload and Test area
        #
        reloadCollapsibleButton = ctk.ctkCollapsibleButton()
        reloadCollapsibleButton.text = "Reload && Test"
        self.layout.addWidget(reloadCollapsibleButton)
        reloadFormLayout = qt.QFormLayout(reloadCollapsibleButton)

        # reload button
        # (use this during development, but remove it when delivering
        #  your module to users)
        self.reloadButton = qt.QPushButton("Reload")
        self.reloadButton.toolTip = "Reload this module."
        self.reloadButton.name = "Freehand3DUltrasound Reload"
        reloadFormLayout.addWidget(self.reloadButton)
        self.reloadButton.connect('clicked()', self.onReload)

        # Instantiate and connect widgets ...
        # Model Repository Area
        self.modelRepositoryCollapsibleGroupBox = ctk.ctkCollapsibleGroupBox()
        self.modelRepositoryCollapsibleGroupBox.setTitle('Cloud Model Repository')
        self.layout.addWidget(self.modelRepositoryCollapsibleGroupBox)
        modelRepositoryVBoxLayout1 = qt.QVBoxLayout(self.modelRepositoryCollapsibleGroupBox)
        modelRepositoryExpdableArea = ctk.ctkExpandableWidget()
        modelRepositoryVBoxLayout1.addWidget(modelRepositoryExpdableArea)
        modelRepositoryVBoxLayout2 = qt.QVBoxLayout(modelRepositoryExpdableArea)
        # modelRepositoryVerticalLayout = qt.QVBoxLayout(modelRepositoryExpdableArea)
        self.modelRepositoryTableWidget = qt.QTableWidget()
        self.modelRepositoryModel = qt.QStandardItemModel()
        self.modelRepositoryTableHeaderLabels = ['Model Name', 'Organ', 'Task', 'Status']
        self.modelRepositoryTableWidget.setColumnCount(4)
        self.modelRepositoryTableWidget.sortingEnabled = True
        self.modelRepositoryTableWidget.setHorizontalHeaderLabels(self.modelRepositoryTableHeaderLabels)
        self.modelRepositoryTableWidgetHeader = self.modelRepositoryTableWidget.horizontalHeader()
        self.modelRepositoryTableWidgetHeader.setStretchLastSection(True)
        # modelRepositoryTableWidgetHeader.setResizeMode(qt.QHeaderView.Stretch)
        modelRepositoryVBoxLayout2.addWidget(self.modelRepositoryTableWidget)
        self.modelRepositoryTreeSelectionModel = self.modelRepositoryTableWidget.selectionModel()
        abstractItemView = qt.QAbstractItemView()
        self.modelRepositoryTableWidget.setSelectionBehavior(abstractItemView.SelectRows)
        verticalheader = self.modelRepositoryTableWidget.verticalHeader()
        verticalheader.setDefaultSectionSize(20)
        modelRepositoryVBoxLayout1.setSpacing(0)
        modelRepositoryVBoxLayout2.setSpacing(0)
        modelRepositoryVBoxLayout1.setMargin(0)
        modelRepositoryVBoxLayout2.setContentsMargins(7, 3, 7, 7)

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

        # add all the models listed in the json files
        for idx, j in enumerate(self.jsonModels):
            name = j["name"]
            self.modelSelector.addItem(name, idx)

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
        self.restoreDefaultsButton.connect('clicked(bool)', self.onRestoreDefaultsButton)
        self.applyButton.connect('clicked(bool)', self.onApplyButton)
        self.cancelButton.connect('clicked(bool)', self.onCancelButton)

        # Initlial Selection
        self.modelSelector.currentIndexChanged(self.modelSelector.currentIndex)

    def cleanup(self):
        pass

    def printPythonCommand(self):
        # self.modelParameters.prerun()  # Do this first!
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

        print "\n".join(printStr)

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
        self.modelParameters.destroy()
        if selectorIndex < 0:
            return
        jsonIndex = self.modelSelector.itemData(selectorIndex)
        json = self.jsonModels[jsonIndex]
        self.modelParameters.create(json)

        if "briefdescription" in self.jsonModels[jsonIndex]:
            tip = self.jsonModels[jsonIndex]["briefdescription"]
            tip = tip.rstrip()
            self.modelSelector.setToolTip(tip)
        else:
            self.modelSelector.setToolTip("")

    def onRestoreDefaultsButton(self):
        self.onModelSelect(self.modelSelector.currentIndex)

    def onApplyButton(self):
        print("on Apply")
        '''
        try:

            self.currentStatusLabel.text = "Starting"

            self.modelParameters.prerun()

            self.logic = DeepInferLogic()

            self.printPythonCommand()

            # print "running..."
            self.logic.run(self.modelParameters.model,
                           self.modelParameters.output,
                           self.modelParameters.outputLabelMap,
                           *self.modelParameters.inputs)

        except:
            self.currentStatusLabel.text = "Exception"

            import sys
            msg = sys.exc_info()[0]

            # if there was an exception during start-up make sure to finish
            self.onLogicRunStop()

            qt.QMessageBox.critical(slicer.util.mainWindow(),
                                    "Exception before execution of {0}".format(self.modelParameters.model.GetName()),
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
        # print "Aborting..."
        self.currentStatusLabel.text = "Aborted"

    def onLogicEventProgress(self, progress):
        self.currentStatusLabel.text = "Running ({0:6.5f})".format(progress)
        self.progress.setValue(progress * 1000)

    def onLogicEventIteration(self, nIter):
        print "Iteration ", nIter


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

    def __del__(self):
        if self.main_queue_running:
            self.main_queue_stop()
        if self.thread.is_alive():
            self.thread.join()

    def yieldPythonGIL(self, seconds=0):
        sleep(seconds)

    def cmdCheckAbort(self, sitkModel):
        if self.abort:
            sitkModel.Abort()

    def cmdStartEvent(self, sitkModel):
        # print "cmStartEvent"
        widget = slicer.modules.DeepInferWidget
        self.main_queue.put(lambda: widget.onLogicEventStart())
        self.yieldPythonGIL()

    def cmdProgressEvent(self, sitkModel):
        # print "cmProgressEvent", sitkModel.GetProgress()
        widget = slicer.modules.DeepInferWidget
        self.main_queue.put(lambda p=sitkModel.GetProgress(): widget.onLogicEventProgress(p))
        self.cmdCheckAbort(sitkModel)
        self.yieldPythonGIL()

    def cmdIterationEvent(self, sitkModel, nIter):
        print "cmIterationEvent"
        widget = slicer.modules.DeepInferWidget
        self.main_queue.put(lambda: widget.onLogicEventIteration(nIter))
        ++nIter;
        self.cmdCheckAbort(sitkModel)
        self.yieldPythonGIL()

    def cmdAbortEvent(self, sitkModel):
        # print "cmAbortEvent"
        widget = slicer.modules.DeepInferWidget
        self.main_queue.put(lambda: widget.onLogicEventAbort())
        self.yieldPythonGIL()

    def cmdEndEvent(self):
        # print "cmEndEvent"
        widget = slicer.modules.DeepInferWidget
        self.main_queue.put(lambda: widget.onLogicEventEnd())
        self.yieldPythonGIL()

    def thread_doit(self, sitkModel, *inputImages):
        print('tread doit')
        '''
        try:

            nIter = 0
            try:
                sitkModel.AddCommand(sitk.sitkStartEvent, lambda: self.cmdStartEvent(sitkModel))
                sitkModel.AddCommand(sitk.sitkProgressEvent, lambda: self.cmdProgressEvent(sitkModel))
                sitkModel.AddCommand(sitk.sitkIterationEvent, lambda: self.cmdIterationEvent(sitkModel, nIter))
                sitkModel.AddCommand(sitk.sitkAbortEvent, lambda: self.cmdAbortEvent(sitkModel))
                sitkModel.AddCommand(sitk.sitkEndEvent, lambda: self.cmdEndEvent())

            except:
                import sys
                print "Unexpected error:", sys.exc_info()[0]

            img = sitkModel.Execute(*inputImages)

            if not self.abort:
                self.main_queue.put(lambda img=img: self.updateOutput(img))

        except Exception as e:
            msg = e.message
            self.abort = True

            self.yieldPythonGIL()
            self.main_queue.put(lambda: qt.QMessageBox.critical(slicer.util.mainWindow(),
                                                                "Exception during execution of {0}".format(
                                                                    sitkModel.GetName()),
                                                                msg))
        finally:
            # this model is persistent, remove commands
            sitkModel.RemoveAllCommands()
            self.main_queue.put(self.main_queue_stop)
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

    def updateOutput(self, img):

        nodeWriteAddress = sitkUtils.GetSlicerITKReadWriteAddress(self.outputNodeName)
        sitk.WriteImage(img, nodeWriteAddress)

        node = slicer.util.getNode(self.outputNodeName)

        applicationLogic = slicer.app.applicationLogic()
        selectionNode = applicationLogic.GetSelectionNode()

        if self.outputLabelMap:
            selectionNode.SetReferenceActiveLabelVolumeID(node.GetID())
        else:
            selectionNode.SetReferenceActiveVolumeID(node.GetID())

        applicationLogic.PropagateVolumeSelection(0)
        applicationLogic.FitSliceToAll()

    def run(self, model, outputMRMLNode, outputLabelMap, *inputs):
        """
        Run the actual algorithm
        """

        print("run")

        if self.thread.is_alive():
            import sys
            sys.stderr.write("ModelLogic is already executing!")
            return

        inputImages = []

        '''
        for i in inputs:
            if i is None:
                break

            imgNodeName = i.GetName()

            img = sitk.ReadImage(sitkUtils.GetSlicerITKReadWriteAddress(imgNodeName))
            inputImages.append(img)

        '''
        self.output = None

        # check
        self.outputNodeName = outputMRMLNode.GetName()
        self.outputLabelMap = outputLabelMap

        self.abort = False

        self.thread = threading.Thread(target=lambda f=model, i=inputImages: self.thread_doit(f, *inputImages))

        self.main_queue_start()
        self.thread.start()


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
        self.json = json
        self.model = None
        self.inputs = []
        self.output = None
        self.prerun_callbacks = []
        self.outputLabelMap = False

        self.outputSelector = None
        self.outputLabelMapBox = None

    def __del__(self):
        self.widgets = []

    def BeautifyCamelCase(self, str):
        return self.reCamelCase.sub(r' \1', str)

    def create(self, json):
        if not self.parent:
            raise "no parent"

        parametersFormLayout = self.parent.layout()

        # You can't use exec in a function that has a subfunction, unless you specify a context.
        # exec ('self.model = sitk.{0}()'.format(json["name"])) in globals(), locals()

        self.prerun_callbacks = []
        self.inputs = []
        self.outputLabelMap = False

        #
        # input volume selectors
        #
        '''
        if "inputs" in json:

            # have named inputs
            n = 0
            for input in json["inputs"]:

                w = self.createInputWidget(n, noneEnabled=("optional" in input and input["optional"]))

                name = "Input Volume: "
                if "name" in input:
                    name = "Input {0}: ".format(input["name"])
                name = name.replace("Image", "Volume")

                print "adding {1}: {0}".format(name, n)
                inputSelectorLabel = qt.QLabel(name)
                self.widgets.append(inputSelectorLabel)

                # add to layout after connection
                parametersFormLayout.addRow(inputSelectorLabel, w)

                self.inputs.append(w.currentNode())

                n += 1

                if "number_of_inputs" in json and json["number_of_inputs"] != 0:
                    import sys
                    sys.stderr.write("Expected \"number_of_inputs\" to be 0 not {0}!".format(json["number_of_inputs"]))

        else:

            for n in range(json["number_of_inputs"]):
                w = self.createInputWidget(n)

                inputSelectorLabel = qt.QLabel("Input Volume: ")
                self.widgets.append(inputSelectorLabel)

                # add to layout after connection
                parametersFormLayout.addRow(inputSelectorLabel, w)

                self.inputs.append(w.currentNode())

                # end for each input

        if json["template_code_filename"] == "KernelImageModel":
            w = self.createVectorWidget("KernelRadius", "std::vector<uint32_t>")
            self.widgets.append(w)
            self.addWidgetWithToolTipAndLabel(w, {"briefdescriptionSet": "Radius of structuring element",
                                                  "name": "KernelRadius"})

            labels = ["Annulus",
                      "Box",
                      "Ball",
                      "Cross"]
            values = ["sitk.sitkAnnulus",
                      "sitk.sitkBox",
                      "sitk.sitkBall",
                      "sitk.sitkCross"]
            w = self.createEnumWidget("KernelType", labels, values)
            self.addWidgetWithToolTipAndLabel(w, {"briefdescriptionSet": "Structuring element", "name": "Kernel Type"})

        elif json["template_code_filename"] == "RegionGrowingImageModel" \
                or json["template_code_filename"] == "FastMarchingImageModel":

            name = "SeedList"
            if (json["template_code_filename"] == "FastMarchingImageModel"):
                name = "TrialPoints"

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
            fiducialSelector.setToolTip("Pick the Markups node for the seed list.")

            fiducialSelector.connect("nodeActivated(vtkMRMLNode*)",
                                     lambda node, name=name: self.onFiducialListNode(name, node))
            self.prerun_callbacks.append(
                lambda w=fiducialSelector, name=name: self.onFiducialListNode(name, w.currentNode()))

            fiducialSelectorLabel = qt.QLabel("{0}: ".format(name))
            self.widgets.append(fiducialSelectorLabel)

            # todo set tool tip
            # add to layout after connection
            parametersFormLayout.addRow(fiducialSelectorLabel, fiducialSelector)

        '''
        #
        # Iterate over the members in the JSON to generate a GUI
        #
        for member in json["members"]:
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

                    icon = qt.QIcon(DeepInfer.ICON_DIR + "Fiducials.png")

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

                    parametersFormLayout.addRow(fiducialSelectorLabel, hlayout)

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
                    lambda w=fiducialSelector, name=member["name"],: self.onFiducialListNode(name, w.currentNode()))

                w = fiducialSelector

            elif "enum" in member:
                w = self.createEnumWidget(member["name"], member["enum"])
            elif member["name"].endswith("Direction") and "std::vector" in t:
                # This member name is use for direction cosine matrix for image sources.
                # We are going to ignore it
                pass
            elif t in ["InputVolume", "OutputVolume"]:
                w = self.createVolumeWidget(member["name"], False)

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
                w = self.createDoubleWidget(member["name"])
            elif t == "bool":
                w = self.createBoolWidget(member["name"])
            elif t in ["uint8_t", "int8_t",
                       "uint16_t", "int16_t",
                       "uint32_t", "int32_t",
                       "uint64_t", "int64_t",
                       "unsigned int", "int"]:
                w = self.createIntWidget(member["name"], t)
            else:
                import sys
                sys.stderr.write("Unknown member \"{0}\" of type \"{1}\"\n".format(member["name"], member["type"]))

            if w:
                self.addWidgetWithToolTipAndLabel(w, member)

        # end for each member


        #
        # output volume selector
        #
        '''
        outputSelectorLabel = qt.QLabel("Output Volume: ")
        self.widgets.append(outputSelectorLabel)

        self.outputSelector = slicer.qMRMLNodeComboBox()
        self.widgets.append(self.outputSelector)
        self.outputSelector.nodeTypes = ["vtkMRMLScalarVolumeNode", "vtkMRMLLabelMapVolumeNode"]
        self.outputSelector.selectNodeUponCreation = True
        self.outputSelector.addEnabled = True
        self.outputSelector.removeEnabled = False
        self.outputSelector.renameEnabled = True
        self.outputSelector.noneEnabled = False
        self.outputSelector.showHidden = False
        self.outputSelector.showChildNodeTypes = False
        self.outputSelector.baseName = json["name"] + " Output"
        self.outputSelector.setMRMLScene(slicer.mrmlScene)
        self.outputSelector.setToolTip("Pick the output to the algorithm.")

        self.outputSelector.connect("nodeActivated(vtkMRMLNode*)", lambda node: self.onOutputSelect(node))

        # add to layout after connection
        parametersFormLayout.addRow(outputSelectorLabel, self.outputSelector)

        self.output = self.outputSelector.currentNode()

        #
        # LabelMap toggle
        #
        outputLabelMapLabel = qt.QLabel("LabelMap: ")
        self.widgets.append(outputLabelMapLabel)

        self.outputLabelMapBox = qt.QCheckBox()
        self.widgets.append(self.outputLabelMapBox)
        self.outputLabelMapBox.setToolTip("Output Volume is set as a labelmap")
        self.outputLabelMapBox.setChecked(self.outputLabelMap)
        self.outputLabelMapBox.setDisabled(True)

        self.outputLabelMapBox.connect("stateChanged(int)", lambda val: self.onOutputLabelMapChanged(bool(val)))
        # add to layout after connection
        parametersFormLayout.addRow(outputLabelMapLabel, self.outputLabelMapBox)
        '''

    def createVolumeWidget(self, name, noneEnabled=False):
        volumeSelector = slicer.qMRMLNodeComboBox()
        self.widgets.append(volumeSelector)
        volumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode", "vtkMRMLLabelMapVolumeNode"]
        volumeSelector.selectNodeUponCreation = True
        volumeSelector.addEnabled = False
        volumeSelector.removeEnabled = False
        volumeSelector.noneEnabled = noneEnabled
        volumeSelector.showHidden = False
        volumeSelector.showChildNodeTypes = False
        volumeSelector.setMRMLScene(slicer.mrmlScene)
        volumeSelector.setToolTip("Pick the volume.")

        # connect and verify parameters
        volumeSelector.connect("nodeActivated(vtkMRMLNode*)", lambda node, n=name: self.onInputSelect(node, n))
        return volumeSelector

    def createEnumWidget(self, name, enumList, valueList=None):

        w = qt.QComboBox()
        self.widgets.append(w)

        # exec 'default=self.model.Get{0}()'.format(name) in globals(), locals()

        if valueList is None:
            valueList = ["self.model." + e for e in enumList]

        for e, v in zip(enumList, valueList):
            w.addItem(e, v)

            # check if current item is default, set if it is
            # exec 'itemValue=' + v in globals(), locals()
            '''
            if itemValue == default:
                w.setCurrentIndex(w.count - 1)
            '''

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

    def createIntWidget(self, name, type="int"):

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
        # w.setValue(int(default))
        w.connect("valueChanged(int)", lambda val, name=name: self.onScalarChanged(name, val))
        return w

    def createBoolWidget(self, name):
        # exec ('default = self.model.Get{0}()'.format(name)) in globals(), locals()
        w = qt.QCheckBox()
        self.widgets.append(w)

        # w.setChecked(default)

        w.connect("stateChanged(int)", lambda val, name=name: self.onScalarChanged(name, bool(val)))

        return w

    def createDoubleWidget(self, name):
        # exec ('default = self.model.Get{0}()'.format(name)) in globals(), locals()
        w = qt.QDoubleSpinBox()
        self.widgets.append(w)

        w.setRange(-3.40282e+038, 3.40282e+038)
        w.decimals = 5

        # w.setValue(default)
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

    def onInputSelect(self, mrmlNode, n):
        self.inputs[n] = mrmlNode

    def onOutputSelect(self, mrmlNode):
        self.output = mrmlNode
        self.onOutputLabelMapChanged(mrmlNode.IsA("vtkMRMLLabelMapVolumeNode"))

    def onOutputLabelMapChanged(self, v):
        self.outputLabelMap = v
        self.outputLabelMapBox.setChecked(v)

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
        print("onScalarChanged")

    def onEnumChanged(self, name, selectorIndex, selector):
        data = selector.itemData(selectorIndex)
        # exec ('self.model.Set{0}({1})'.format(name, data))

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
        for f in self.prerun_callbacks:
            f()

    def destroy(self):

        for w in self.widgets:
            # self.parent.layout().removeWidget(w)
            w.deleteLater()
            w.setParent(None)
        self.widgets = []
