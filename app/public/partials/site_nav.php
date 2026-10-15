<?php
declare(strict_types=1);

$currentPage = basename((string)($_SERVER['PHP_SELF'] ?? ''));

$oddbNavItems = [
    ['label' => 'Home',          'href' => 'index.php',         'page' => 'index.php'],
    ['label' => 'Explore',       'href' => 'explore.php',       'page' => 'explore.php'],
    ['label' => 'Statistics',    'href' => 'statistics.php',    'page' => 'statistics.php'],
    ['label' => 'Data & release','href' => 'data.php',          'page' => 'data.php'],
    ['label' => 'Documentation', 'href' => 'documentation.php', 'page' => 'documentation.php'],
    ['label' => 'Contact',       'href' => 'contact.php',       'page' => 'contact.php'],
];

function oddb_nav_active(string $page, string $currentPage): string {
    return $page === $currentPage ? ' active' : '';
}
?>
<nav class="oddb-site-nav" aria-label="Primary navigation">
 <div class="oddb-nav-inner">
  <a class="oddb-nav-brand" href="index.php" aria-label="ODDB home">
   <img src="assets/oddb-nav-logo-v0.8.3.svg" width="162" height="48" alt="ODDB" style="display:block">
  </a>

  <button class="oddb-nav-toggle"
          type="button"
          aria-expanded="false"
          aria-controls="oddbPrimaryMenu"
          aria-label="Open navigation">
   <span></span><span></span><span></span>
  </button>

  <div class="oddb-nav-menu" id="oddbPrimaryMenu">
   <?php foreach ($oddbNavItems as $item): ?>
    <a class="oddb-nav-link<?= oddb_nav_active($item['page'], $currentPage) ?>"
       href="<?= htmlspecialchars($item['href'], ENT_QUOTES, 'UTF-8') ?>"
       <?= $item['page'] === $currentPage ? 'aria-current="page"' : '' ?>>
     <?= htmlspecialchars($item['label'], ENT_QUOTES, 'UTF-8') ?>
    </a>
   <?php endforeach; ?>

   <a class="oddb-nav-link oddb-nav-about"
      href="index.php#about">About</a>
  </div>
 </div>
</nav>

<!-- ODDB_VISITORS_23: page-name-only analytics -->
<script src="assets/visitor-track23.js?v=23" defer></script>
