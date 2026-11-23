package compat;

import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;
import java.awt.event.MouseAdapter;
import java.awt.event.MouseEvent;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;
import javax.swing.Timer;

/**
 * Second source-backed SwingJS fixture.
 *
 * Exercises Swing layout, JButton/JLabel, mouse input, Swing Timer, and
 * Graphics2D drawing without depending on SwingJS-specific APIs.
 */
public class WidgetDemo extends JPanel implements ActionListener {

    private static final long serialVersionUID = 1L;
    private static final int WIDTH = 800;
    private static final int HEIGHT = 600;

    private final Timer timer;
    private final JButton toggle = new JButton("Pause");
    private final JLabel status = new JLabel("starting");
    private int ticks;
    private int clicks;
    private double phase;
    private boolean running = true;

    public WidgetDemo() {
        setPreferredSize(new Dimension(WIDTH, HEIGHT));
        setBackground(new Color(8, 15, 30));
        setLayout(new BorderLayout());

        JPanel controls = new JPanel();
        controls.setBackground(new Color(15, 23, 42));
        toggle.setFocusable(false);
        status.setForeground(new Color(226, 232, 240));
        status.setFont(new Font("SansSerif", Font.PLAIN, 14));
        controls.add(toggle);
        controls.add(status);
        add(controls, BorderLayout.SOUTH);

        toggle.addActionListener(new ActionListener() {
            @Override
            public void actionPerformed(ActionEvent event) {
                running = !running;
                toggle.setText(running ? "Pause" : "Resume");
                publish("toggle");
            }
        });
        addMouseListener(new MouseAdapter() {
            @Override
            public void mousePressed(MouseEvent event) {
                clicks++;
                phase += 0.8;
                publish("click");
                repaint();
            }
        });

        timer = new Timer(30, this);
        timer.start();
        publish("start");
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(new Runnable() {
            @Override
            public void run() {
                JFrame frame = new JFrame("Provikom SwingJS Widget Fixture");
                frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
                frame.setContentPane(new WidgetDemo());
                frame.pack();
                frame.setLocation(40, 40);
                frame.setVisible(true);
            }
        });
    }

    @Override
    public void actionPerformed(ActionEvent event) {
        if (running) {
            ticks++;
            phase += 0.035;
            if (ticks % 20 == 0) {
                publish("tick");
            }
        }
        repaint();
    }

    private void publish(String reason) {
        status.setText(reason + "  ticks=" + ticks + "  clicks=" + clicks);
        System.out.println(
                "FIXTURE ticks=" + ticks + " clicks=" + clicks
                        + " phase=" + String.format("%.3f", phase)
                        + " running=" + running);
    }

    @Override
    protected void paintComponent(Graphics graphics) {
        super.paintComponent(graphics);
        Graphics2D g = (Graphics2D) graphics.create();
        try {
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            int width = getWidth();
            int height = Math.max(1, getHeight() - 48);

            g.setColor(new Color(15, 23, 42));
            g.fillRect(0, 0, width, height);
            for (int x = 0; x < width; x += 32) {
                g.setColor(new Color(24, 35, 56));
                g.drawLine(x, 0, x, height);
            }
            for (int y = 0; y < height; y += 32) {
                g.setColor(new Color(24, 35, 56));
                g.drawLine(0, y, width, y);
            }

            int bars = 14;
            int gap = 8;
            int barWidth = Math.max(8, (width - gap * (bars + 1)) / bars);
            for (int i = 0; i < bars; i++) {
                double wave = Math.sin(phase + i * 0.45);
                int barHeight = (int) ((height * 0.28) + (height * 0.2) * (wave + 1.0));
                int x = gap + i * (barWidth + gap);
                int y = height - barHeight;
                g.setColor(new Color(30 + i * 10, 110 + (i * 11) % 120, 220 - i * 8));
                g.fillRoundRect(x, y, barWidth, barHeight, 10, 10);
            }

            int cx = (int) (width / 2 + Math.cos(phase) * width * 0.32);
            int cy = (int) (height / 2 + Math.sin(phase * 1.3) * height * 0.26);
            g.setColor(new Color(250, 204, 21));
            g.fillOval(cx - 24, cy - 24, 48, 48);
            g.setColor(new Color(15, 23, 42));
            g.fillOval(cx - 10, cy - 10, 20, 20);

            g.setColor(new Color(226, 232, 240));
            g.setFont(new Font("SansSerif", Font.BOLD, 22));
            g.drawString("SwingJS Widget Compatibility Fixture", 24, 42);
            g.setFont(new Font("SansSerif", Font.PLAIN, 14));
            g.setColor(new Color(148, 163, 184));
            g.drawString("JButton + JLabel + Mouse + Timer + Graphics2D", 24, 68);
            g.setColor(running ? new Color(74, 222, 128) : new Color(248, 113, 113));
            g.drawString(running ? "RUNNING" : "PAUSED", width - 120, 42);
        } finally {
            g.dispose();
        }
    }
}
