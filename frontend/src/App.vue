<script setup>
</script>

<template>
  <header class="nav">
    <strong>Reto Innovación</strong>
    <nav>
      <RouterLink to="/">Chat</RouterLink>
      <RouterLink to="/panel">Panel</RouterLink>
    </nav>
  </header>
  <main>
    <RouterView />
  </main>
</template>

<style>
body {
  font-family: system-ui, sans-serif;
  margin: 0;
  color: #222;
}
.nav {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid #e0e0e0;
}
.nav nav {
  display: flex;
  gap: 1rem;
}
.nav a {
  color: #444;
  text-decoration: none;
}
.nav a.router-link-active {
  font-weight: 600;
  color: #000;
}
main {
  padding: 1.5rem;
}
</style>
