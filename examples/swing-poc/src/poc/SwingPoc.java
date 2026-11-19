package poc;

import java.awt.Color;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;
import java.awt.event.KeyEvent;
import javax.swing.AbstractAction;
import javax.swing.JComponent;
import javax.swing.JFrame;
import javax.swing.JPanel;
import javax.swing.KeyStroke;
import javax.swing.SwingUtilities;
import javax.swing.Timer;

/**
 * Minimal Java 8 Swing application used to evaluate Java2Script/SwingJS.
 *
 * This class deliberately uses only APIs that must be exercised by Milestone
 * 2C.0: JFrame, JPanel, Graphics2D, Swing Timer, keyboard input, and a moving
 * object. It has no build-time dependency on SwingJS or CheerpJ.
 */
public class SwingPoc extends JPanel implements ActionListener {

    private static final long serialVersionUID = 1L;

    public static final String TITLE = "Provikom SwingJS POC";
    public static final int WIDTH = 720;
    public static final int HEIGHT = 540;

    private final Timer timer;
    private int x = 80;
    private int y = 200;
    private int dx = 4;
    private int dy = 3;
    private int radius = 22;
    private int ticks;
    private boolean paused;
    private int lastActionCode;
    private long lastActionAt;

    public SwingPoc() {
        setPreferredSize(new Dimension(WIDTH, HEIGHT));
        setBackground(new Color(15, 23, 42));
        setFocusable(true);
        bindKey("left", KeyEvent.VK_LEFT);
        bindKey("right", KeyEvent.VK_RIGHT);
        bindKey("up", KeyEvent.VK_UP);
        bindKey("down", KeyEvent.VK_DOWN);
        bindKey("pause", KeyEvent.VK_SPACE);
        bindKey("pause-alt", KeyEvent.VK_P);
        bindKey("reset", KeyEvent.VK_R);
        timer = new Timer(20, this);
        timer.start();
        publishState();
    }

    private void bindKey(String name, final int keyCode) {
        getInputMap(JComponent.WHEN_IN_FOCUSED_WINDOW).put(KeyStroke.getKeyStroke(keyCode, 0), name);
        getActionMap().put(name, new AbstractAction() {
            private static final long serialVersionUID = 1L;

            @Override
            public void actionPerformed(ActionEvent event) {
                handleKey(keyCode);
            }
        });
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(new Runnable() {
            @Override
            public void run() {
                createAndShow();
            }
        });
    }

    public static JFrame createAndShow() {
        JFrame frame = new JFrame(TITLE);
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        SwingPoc panel = new SwingPoc();
        frame.setContentPane(panel);
        frame.pack();
        frame.setLocation(40, 40);
        frame.setVisible(true);
        panel.requestFocusInWindow();
        panel.publishState();
        return frame;
    }

    public SwingPoc getPlayfield() {
        return this;
    }

    public int getXPosition() {
        return x;
    }

    public int getYPosition() {
        return y;
    }

    public int getDx() {
        return dx;
    }

    public int getDy() {
        return dy;
    }

    public int getTicks() {
        return ticks;
    }

    public boolean isPaused() {
        return paused;
    }

    public void handleKey(int keyCode) {
        if (keyCode == KeyEvent.VK_LEFT) {
            dx = -Math.max(2, Math.abs(dx));
        } else if (keyCode == KeyEvent.VK_RIGHT) {
            dx = Math.max(2, Math.abs(dx));
        } else if (keyCode == KeyEvent.VK_UP) {
            dy = -Math.max(2, Math.abs(dy));
        } else if (keyCode == KeyEvent.VK_DOWN) {
            dy = Math.max(2, Math.abs(dy));
        } else if (keyCode == KeyEvent.VK_SPACE || keyCode == KeyEvent.VK_P) {
            if (consumeDuplicateAction(keyCode)) {
                return;
            }
            paused = !paused;
        } else if (keyCode == KeyEvent.VK_R) {
            if (consumeDuplicateAction(keyCode)) {
                return;
            }
            reset();
        } else {
            return;
        }
        publishState();
    }

    // SwingJS can surface one browser key press as both keydown and keypress.
    private boolean consumeDuplicateAction(int keyCode) {
        long now = System.currentTimeMillis();
        if (keyCode == lastActionCode && now - lastActionAt < 300) {
            return true;
        }
        lastActionCode = keyCode;
        lastActionAt = now;
        return false;
    }

    private void reset() {
        x = 80;
        y = 200;
        dx = 4;
        dy = 3;
        ticks = 0;
        paused = false;
    }

    @Override
    public void actionPerformed(ActionEvent event) {
        if (!paused) {
            ticks++;
            x += dx;
            y += dy;
            int minX = radius;
            int maxX = getWidth() - radius;
            int minY = radius + 42;
            int maxY = getHeight() - radius - 24;
            if (maxX <= minX) {
                maxX = WIDTH - radius;
            }
            if (maxY <= minY) {
                maxY = HEIGHT - radius - 24;
            }
            if (x < minX) {
                x = minX;
                dx = Math.abs(dx);
            } else if (x > maxX) {
                x = maxX;
                dx = -Math.abs(dx);
            }
            if (y < minY) {
                y = minY;
                dy = Math.abs(dy);
            } else if (y > maxY) {
                y = maxY;
                dy = -Math.abs(dy);
            }
            if (ticks % 20 == 0) {
                publishState();
            }
        }
        repaint();
    }

    @Override
    protected void paintComponent(Graphics graphics) {
        super.paintComponent(graphics);
        Graphics2D g = (Graphics2D) graphics.create();
        try {
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);

            g.setColor(new Color(30, 41, 59));
            for (int gx = 0; gx < getWidth(); gx += 40) {
                g.drawLine(gx, 0, gx, getHeight());
            }
            for (int gy = 0; gy < getHeight(); gy += 40) {
                g.drawLine(0, gy, getWidth(), gy);
            }

            g.setColor(new Color(56, 189, 248));
            g.fillOval(x - radius, y - radius, radius * 2, radius * 2);
            g.setColor(new Color(224, 242, 254));
            g.fillOval(x - radius / 3, y - radius / 3, radius * 2 / 3, radius * 2 / 3);

            g.setColor(new Color(15, 23, 42));
            g.fillRect(0, 0, getWidth(), 40);
            g.setColor(new Color(226, 232, 240));
            g.setFont(new Font("SansSerif", Font.BOLD, 18));
            g.drawString(TITLE, 16, 26);
            g.setFont(new Font("SansSerif", Font.PLAIN, 13));
            g.setColor(new Color(148, 163, 184));
            g.drawString("Arrows: direction   Space: pause   R: reset", 16, 58);
            g.drawString("x=" + x + "  y=" + y + "  dx=" + dx + "  dy=" + dy + "  ticks=" + ticks,
                    16, getHeight() - 16);

            if (paused) {
                g.setColor(new Color(250, 204, 21));
                g.setFont(new Font("SansSerif", Font.BOLD, 34));
                g.drawString("PAUSED", getWidth() / 2 - 78, getHeight() / 2 + 10);
            }
        } finally {
            g.dispose();
        }
    }

    public void publishState() {
        String line = "STATE x=" + x + " y=" + y + " dx=" + dx + " dy=" + dy
                + " paused=" + paused + " ticks=" + ticks;
        System.out.println(line);
    }
}
