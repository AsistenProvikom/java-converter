package poc;

import java.awt.Graphics2D;
import java.awt.event.KeyEvent;
import java.awt.image.BufferedImage;
import java.io.File;
import javax.imageio.ImageIO;
import javax.swing.JFrame;
import javax.swing.SwingUtilities;

/**
 * Host-only desktop smoke test for SwingPoc.
 *
 * Run under a display (or Xvfb) after compiling src/ and test/. This class is
 * intentionally not part of the transpiled source tree.
 */
public final class DesktopSmokeTest {

    private DesktopSmokeTest() {
    }

    public static void main(String[] args) throws Exception {
        try {
            run(args);
        } catch (Throwable failure) {
            failure.printStackTrace();
            System.exit(1);
        }
    }

    private static void run(String[] args) throws Exception {
        final SwingPoc[] app = new SwingPoc[1];
        final JFrame[] frame = new JFrame[1];

        SwingUtilities.invokeAndWait(new Runnable() {
            @Override
            public void run() {
                frame[0] = SwingPoc.createAndShow();
                app[0] = (SwingPoc) frame[0].getContentPane();
            }
        });

        Thread.sleep(1500);
        if (!frame[0].isVisible()) {
            throw new AssertionError("SwingPoc frame is not visible");
        }
        if (!SwingPoc.TITLE.equals(frame[0].getTitle())) {
            throw new AssertionError("Unexpected frame title: " + frame[0].getTitle());
        }
        if (frame[0].getWidth() < SwingPoc.WIDTH || frame[0].getHeight() < SwingPoc.HEIGHT) {
            throw new AssertionError("Unexpected frame size: " + frame[0].getSize());
        }

        int ticksBefore = app[0].getTicks();
        Thread.sleep(300);
        if (app[0].getTicks() <= ticksBefore) {
            throw new AssertionError("Swing Timer did not advance the simulation");
        }

        int xBefore = app[0].getXPosition();
        app[0].handleKey(KeyEvent.VK_RIGHT);
        Thread.sleep(300);
        if (app[0].getXPosition() <= xBefore) {
            throw new AssertionError("Right arrow did not move the object right");
        }

        app[0].handleKey(KeyEvent.VK_SPACE);
        Thread.sleep(120);
        int pausedTicks = app[0].getTicks();
        Thread.sleep(300);
        if (!app[0].isPaused() || app[0].getTicks() != pausedTicks) {
            throw new AssertionError("Space did not pause the simulation");
        }

        app[0].handleKey(KeyEvent.VK_R);
        if (app[0].isPaused() || app[0].getTicks() > 5
                || app[0].getXPosition() < 80 || app[0].getXPosition() > 110
                || app[0].getYPosition() < 200 || app[0].getYPosition() > 230) {
            throw new AssertionError("R did not reset the simulation: x="
                    + app[0].getXPosition() + " y=" + app[0].getYPosition()
                    + " ticks=" + app[0].getTicks() + " paused=" + app[0].isPaused());
        }

        File output = new File(args.length > 0 ? args[0] : "desktop-poc.png");
        File parent = output.getAbsoluteFile().getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }
        final BufferedImage image = new BufferedImage(
                frame[0].getWidth(), frame[0].getHeight(), BufferedImage.TYPE_INT_ARGB);
        SwingUtilities.invokeAndWait(new Runnable() {
            @Override
            public void run() {
                Graphics2D graphics = image.createGraphics();
                try {
                    frame[0].paintAll(graphics);
                } finally {
                    graphics.dispose();
                }
            }
        });
        ImageIO.write(image, "png", output);

        System.out.println("DESKTOP_SMOKE_OK frame=" + frame[0].getSize()
                + " ticks=" + app[0].getTicks() + " screenshot=" + output.getPath());

        SwingUtilities.invokeAndWait(new Runnable() {
            @Override
            public void run() {
                frame[0].dispose();
            }
        });
        System.exit(0);
    }
}
