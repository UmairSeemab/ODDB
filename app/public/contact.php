<?php
declare(strict_types=1);

session_start();

function h(string $value): string {
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function new_captcha(): void {
    $a = random_int(2, 9);
    $b = random_int(2, 9);
    $_SESSION['contact_captcha_a'] = $a;
    $_SESSION['contact_captcha_b'] = $b;
    $_SESSION['contact_captcha_answer'] = $a + $b;
}

function csrf_token(): string {
    if (empty($_SESSION['contact_csrf'])) {
        $_SESSION['contact_csrf'] = bin2hex(random_bytes(32));
    }
    return (string)$_SESSION['contact_csrf'];
}

function clean_header_value(string $value): string {
    return trim(str_replace(["\r", "\n"], ' ', $value));
}

function send_contact_mail(
    string $to,
    string $from,
    string $replyTo,
    string $subject,
    string $message
): bool {
    $mailSubject = '[ODDB Contact] '.clean_header_value($subject);

    $body =
        "New message from the ODDB website contact form\n\n".
        "Reply email: ".$replyTo."\n".
        "Subject: ".$subject."\n\n".
        "Message:\n".
        $message."\n\n".
        "----\n".
        "Sent through the ODDB v1 website contact form.\n";

    $headers = [
        'From: ODDB Website <'.$from.'>',
        'Reply-To: '.$replyTo,
        'MIME-Version: 1.0',
        'Content-Type: text/plain; charset=UTF-8',
        'X-Mailer: PHP/'.PHP_VERSION,
    ];

    return mail($to, $mailSubject, $body, implode("\r\n", $headers));
}

$contactTo = trim((string)getenv('ODDB_CONTACT_TO'));
$contactFrom = trim((string)(getenv('ODDB_CONTACT_FROM') ?: 'noreply@oculardiseases.fi'));

$errors = [];
$success = isset($_GET['sent']) && $_GET['sent'] === '1';

$email = '';
$subject = '';
$message = '';

if (!isset($_SESSION['contact_captcha_answer'])) {
    new_captcha();
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $email = trim((string)($_POST['email'] ?? ''));
    $subject = trim((string)($_POST['subject'] ?? ''));
    $message = trim((string)($_POST['message'] ?? ''));
    $captcha = trim((string)($_POST['captcha'] ?? ''));
    $honeypot = trim((string)($_POST['website'] ?? ''));
    $postedToken = (string)($_POST['csrf'] ?? '');

    if (!hash_equals(csrf_token(), $postedToken)) {
        $errors[] = 'The form session expired. Please try again.';
    }

    if ($honeypot !== '') {
        $errors[] = 'The message could not be submitted.';
    }

    if (!filter_var($email, FILTER_VALIDATE_EMAIL) || strlen($email) > 254) {
        $errors[] = 'Please enter a valid email address.';
    }

    if ($subject === '' || mb_strlen($subject) > 180) {
        $errors[] = 'Please enter a subject of 180 characters or fewer.';
    }

    if ($message === '' || mb_strlen($message) > 5000) {
        $errors[] = 'Please enter a message of 5,000 characters or fewer.';
    }

    $expected = (int)($_SESSION['contact_captcha_answer'] ?? -1);
    if ($captcha === '' || !ctype_digit($captcha) || (int)$captcha !== $expected) {
        $errors[] = 'The arithmetic answer was incorrect.';
    }

    $lastSent = (int)($_SESSION['contact_last_sent'] ?? 0);
    if ($lastSent > 0 && (time() - $lastSent) < 60) {
        $errors[] = 'Please wait at least one minute before sending another message.';
    }

    if ($contactTo === '' || !filter_var($contactTo, FILTER_VALIDATE_EMAIL)) {
        $errors[] = 'The contact form recipient has not yet been configured by the site administrator.';
    }

    if (!filter_var($contactFrom, FILTER_VALIDATE_EMAIL)) {
        $errors[] = 'The contact form sender address is not configured correctly.';
    }

    if (!$errors) {
        $safeSubject = clean_header_value($subject);

        $sent = send_contact_mail(
            $contactTo,
            $contactFrom,
            $email,
            $safeSubject,
            $message
        );

        if ($sent) {
            $_SESSION['contact_last_sent'] = time();
            new_captcha();
            header('Location: contact.php?sent=1', true, 303);
            exit;
        }

        $errors[] = 'The message could not be sent by the server. Please try again later.';
    }

    // Always rotate the arithmetic challenge after a failed submission.
    new_captcha();
}

$captchaA = (int)($_SESSION['contact_captcha_a'] ?? 0);
$captchaB = (int)($_SESSION['contact_captcha_b'] ?? 0);
$token = csrf_token();
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="Contact the ODDB v1 team about data, technical issues, corrections or collaboration.">
<title>Contact — ODDB v1</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="assets/contact.css" rel="stylesheet">
<link href="assets/site-nav.css" rel="stylesheet">
<link href="assets/visual-refresh.css?v=0.8.0" rel="stylesheet">
</head>
<body class="oddb-visual oddb-contact">

<?php require __DIR__ . "/partials/site_nav.php"; ?>

<header class="contact-hero">
 <div class="container py-4 py-md-5">
  <div class="eyebrow">ODDB v1</div>
  <h1 class="display-5 fw-bold mb-2">Contact us</h1>
  <p class="lead text-secondary mb-0">
   Send questions about ODDB data, corrections, technical issues or research collaboration.
  </p>
 </div>
</header>

<main class="container py-4 py-md-5">
 <div class="contact-layout">
  <section class="contact-card">
   <div class="eyebrow">Send a message</div>
   <h2 class="h4 fw-bold mt-1 mb-3">Contact the ODDB team</h2>

   <?php if ($success): ?>
    <div class="alert alert-success" role="status">
     <strong>Message sent.</strong> Thank you for contacting ODDB.
    </div>
   <?php endif; ?>

   <?php if ($errors): ?>
    <div class="alert alert-danger" role="alert">
     <strong>Please correct the following:</strong>
     <ul class="mb-0 mt-2">
      <?php foreach ($errors as $error): ?>
       <li><?= h($error) ?></li>
      <?php endforeach; ?>
     </ul>
    </div>
   <?php endif; ?>

   <form method="post" action="contact.php" class="contact-form" novalidate>
    <input type="hidden" name="csrf" value="<?= h($token) ?>">

    <div class="contact-honeypot" aria-hidden="true">
     <label for="website">Website</label>
     <input id="website" name="website" type="text" tabindex="-1" autocomplete="off">
    </div>

    <div>
     <label class="form-label fw-semibold" for="email">Your email</label>
     <input
      class="form-control"
      id="email"
      name="email"
      type="email"
      maxlength="254"
      autocomplete="email"
      required
      value="<?= h($email) ?>"
      placeholder="name@example.com">
    </div>

    <div>
     <label class="form-label fw-semibold" for="subject">Subject</label>
     <input
      class="form-control"
      id="subject"
      name="subject"
      type="text"
      maxlength="180"
      required
      value="<?= h($subject) ?>"
      placeholder="Question about ODDB data">
    </div>

    <div>
     <label class="form-label fw-semibold" for="message">Message</label>
     <textarea
      class="form-control"
      id="message"
      name="message"
      rows="8"
      maxlength="5000"
      required
      placeholder="Write your message here…"><?= h($message) ?></textarea>
     <div class="form-text">Maximum 5,000 characters.</div>
    </div>

    <div class="captcha-box">
     <div>
      <label class="form-label fw-semibold mb-1" for="captcha">Human check</label>
      <div class="captcha-question">
       What is <strong><?= $captchaA ?> + <?= $captchaB ?></strong>?
      </div>
      <div class="form-text">Enter the answer before sending the message.</div>
     </div>
     <input
      class="form-control captcha-input"
      id="captcha"
      name="captcha"
      type="text"
      inputmode="numeric"
      pattern="[0-9]*"
      maxlength="3"
      required
      aria-label="Answer to arithmetic question">
    </div>

    <button class="btn btn-primary contact-submit" type="submit">
     Send message
    </button>
   </form>
  </section>

  <aside class="contact-side">
   <article class="info-card">
    <div class="eyebrow">Good reasons to contact us</div>
    <h2 class="h5 fw-bold mt-1">How we can help</h2>
    <ul class="contact-list">
     <li>Report a data inconsistency or possible curation issue</li>
     <li>Ask about ODDB entities, relationships or evidence interpretation</li>
     <li>Report a website or download problem</li>
     <li>Discuss research use, collaboration or data integration</li>
    </ul>
   </article>

   <article class="info-card">
    <div class="eyebrow">Privacy</div>
    <h2 class="h5 fw-bold mt-1">Please avoid sensitive information</h2>
    <p class="small text-secondary mb-0">
     ODDB is a research resource and does not require patient information. Please do not include personal health information, passwords, or other sensitive data in your message.
    </p>
   </article>

   <article class="info-card">
    <div class="eyebrow">Spam protection</div>
    <h2 class="h5 fw-bold mt-1">Human verification</h2>
    <p class="small text-secondary mb-0">
     The form uses a simple arithmetic challenge, a hidden bot field, CSRF protection and a short submission cooldown. These measures reduce automated spam without requiring an external CAPTCHA service.
    </p>
   </article>
  </aside>
 </div>
</main>

<footer class="site-footer">
 <div class="container py-4 d-flex flex-column flex-md-row justify-content-between gap-2">
  <div class="small text-secondary">ODDB v1 · Ocular Disease Database</div>
  <div class="small text-secondary">Research resource · not clinical guidance</div>
 </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js"></script>
<script src="assets/site-nav.js"></script>
</body>
</html>
