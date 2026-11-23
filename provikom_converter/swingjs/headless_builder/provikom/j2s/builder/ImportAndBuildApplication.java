package provikom.j2s.builder;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

import org.eclipse.core.resources.ICommand;
import org.eclipse.core.resources.IMarker;
import org.eclipse.core.resources.IProject;
import org.eclipse.core.resources.IProjectDescription;
import org.eclipse.core.resources.IResource;
import org.eclipse.core.resources.IWorkspace;
import org.eclipse.core.resources.IWorkspaceRoot;
import org.eclipse.core.resources.IncrementalProjectBuilder;
import org.eclipse.core.resources.ResourcesPlugin;
import org.eclipse.core.runtime.IPath;
import org.eclipse.core.runtime.Path;
import org.eclipse.equinox.app.IApplication;
import org.eclipse.equinox.app.IApplicationContext;

/**
 * Minimal headless Eclipse application that imports an existing Java project
 * and runs a full JDT build. The Java2Script plug-in is a JDT compilation
 * participant, so it runs during this build without opening the Eclipse GUI.
 */
public class ImportAndBuildApplication implements IApplication {

    @Override
    public Object start(IApplicationContext context) throws Exception {
        String projectPath = System.getProperty("provikom.project");
        if (projectPath == null || projectPath.isEmpty()) {
            System.err.println("provikom.project system property is required");
            return 2;
        }
        File projectDir = new File(projectPath).getAbsoluteFile();
        if (!projectDir.isDirectory()) {
            System.err.println("Project directory does not exist: " + projectDir);
            return 2;
        }

        IWorkspace workspace = ResourcesPlugin.getWorkspace();
        IWorkspaceRoot root = workspace.getRoot();
        String name = projectDir.getName();
        IProject project = root.getProject(name);
        if (project.exists()) {
            project.delete(false, true, null);
        }

        IProjectDescription description = workspace.newProjectDescription(name);
        IPath location = Path.fromOSString(projectDir.getAbsolutePath());
        description.setLocation(location);
        description.setNatureIds(new String[] { "org.eclipse.jdt.core.javanature" });
        ICommand command = description.newCommand();
        command.setBuilderName("org.eclipse.jdt.core.javabuilder");
        description.setBuildSpec(new ICommand[] { command });
        project.create(description, null);
        project.open(null);
        project.refreshLocal(IResource.DEPTH_INFINITE, null);

        System.out.println("PROVIKOM_PROJECT=" + project.getName());
        System.out.println("PROVIKOM_LOCATION=" + project.getLocation());
        workspace.build(IncrementalProjectBuilder.FULL_BUILD, null);

        List<String> errors = new ArrayList<String>();
        IMarker[] markers = project.findMarkers(IMarker.PROBLEM, true, IResource.DEPTH_INFINITE);
        for (IMarker marker : markers) {
            int severity = marker.getAttribute(IMarker.SEVERITY, -1);
            if (severity == IMarker.SEVERITY_ERROR) {
                errors.add(marker.getAttribute(IMarker.MESSAGE, "(no message)") + " @ "
                        + marker.getAttribute(IMarker.LOCATION, "?"));
            }
        }
        if (!errors.isEmpty()) {
            for (String error : errors) {
                System.err.println("PROVIKOM_BUILD_ERROR=" + error);
            }
            return 1;
        }
        System.out.println("PROVIKOM_BUILD_OK");
        return IApplication.EXIT_OK;
    }

    @Override
    public void stop() {
    }
}
